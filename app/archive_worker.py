from typing import List, Dict, Optional, Tuple
import uuid
from datetime import datetime
import logging

from sqlmodel import select
from sqlalchemy import delete
from sqlmodel import Session

from .database import SessionLocal
from .models import Sale, Product, SalesArchiveSummary

logger = logging.getLogger("archive_worker")


def archive_batches_once(batch_size: int = 200) -> Optional[Tuple[str, int]]:
    """
    Archiva hasta `batch_size` ventas más recientes en SalesArchiveSummary.
    Devuelve (batch_id, archived_count) o None si no había ventas.
    """
    session: Session = SessionLocal()
    try:
        q = select(Sale).order_by(Sale.hora.desc()).limit(batch_size)
        sales: List[Sale] = session.exec(q).all()

        if not sales:
            return None

        ids_to_delete: List[int] = [s.id for s in sales if s.id is not None]
        if not ids_to_delete:
            return None

        # Agrupar por producto (ventas sin producto se agrupan por venta única)
        grouped: Dict[str, Dict] = {}
        for s in sales:
            raw_pid = getattr(s, "producto_id", None)
            try:
                pid_int = int(raw_pid) if raw_pid is not None else None
            except Exception:
                pid_int = None

            if pid_int and pid_int > 0:
                key = f"p{pid_int}"
                producto_id_for_summary: Optional[int] = pid_int
            else:
                key = f"v{(s.id or uuid.uuid4().int)}"
                producto_id_for_summary = None

            cantidad = int(getattr(s, "cantidad", 1) or 0)
            ingresos = float(getattr(s, "total", 0.0) or 0.0)

            if key not in grouped:
                grouped[key] = {
                    "producto_id": producto_id_for_summary,
                    "nombre": (getattr(s, "nombre", "") or "")[:250],
                    "cantidad_total": 0,
                    "ingresos": 0.0,
                    "costos": 0.0,
                    "ganancia": 0.0,
                    "min_hora": getattr(s, "hora", None),
                    "max_hora": getattr(s, "hora", None),
                }

            g = grouped[key]
            g["cantidad_total"] += cantidad

            costo_unitario = 0.0
            if g["producto_id"] is not None:
                prod: Optional[Product] = session.get(Product, int(g["producto_id"]))
                costo_unitario = float(getattr(prod, "costo_unitario", 0.0) or 0.0) if prod else 0.0

            costos = costo_unitario * cantidad
            g["ingresos"] += ingresos
            g["costos"] += costos
            g["ganancia"] += (ingresos - costos)

            hora = getattr(s, "hora", None)
            if hora:
                if g["min_hora"] is None or hora < g["min_hora"]:
                    g["min_hora"] = hora
                if g["max_hora"] is None or hora > g["max_hora"]:
                    g["max_hora"] = hora

        batch_id = str(uuid.uuid4())
        now = datetime.utcnow()
        summaries: List[SalesArchiveSummary] = []
        for _, g in grouped.items():
            summaries.append(
                SalesArchiveSummary(
                    batch_id=batch_id,
                    producto_id=int(g["producto_id"]) if isinstance(g["producto_id"], int) else None,
                    nombre=g.get("nombre") or "",
                    cantidad_total=int(g.get("cantidad_total", 0)),
                    ingresos=float(g.get("ingresos", 0.0)),
                    costos=float(g.get("costos", 0.0)),
                    ganancia=float(g.get("ganancia", 0.0)),
                    min_hora=g.get("min_hora"),
                    max_hora=g.get("max_hora"),
                    created_at=now,
                )
            )

        # Insertar resúmenes y borrar ventas procesadas; commit explícito
        for s in summaries:
            session.add(s)
        session.exec(delete(Sale).where(Sale.id.in_(ids_to_delete)))
        session.commit()

        archived_count = len(ids_to_delete)
        logger.info("Archived batch %s (%d sales -> %d summaries)", batch_id, archived_count, len(summaries))
        return (batch_id, archived_count)

    except Exception:
        try:
            session.rollback()
        except Exception:
            logger.exception("rollback failed")
        logger.exception("archive_batches_once failed")
        raise
    finally:
        session.close()