from typing import List, Dict, Any, Optional
import logging
import traceback
from app.security import require_role
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel import Session
from sqlalchemy import delete

from ..database import get_session
from ..models import SalesArchiveSummary
from ..archive_worker import archive_batches_once

logger = logging.getLogger("archive_router")

router = APIRouter(prefix="/api/archive", tags=["archive"], dependencies=[Depends(require_role(["admin"]))])



@router.get("/batches")
def list_batches(db: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """
    Lista batches agrupando los SalesArchiveSummary por batch_id.
    Devuelve: [{ batch_id, created_at, total_ingresos, total_ganancia, total_items, min_hora, max_hora }, ...]
    """
    rows = db.exec(select(SalesArchiveSummary)).all()
    if not rows:
        return []

    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        bid = r.batch_id
        g = grouped.get(bid)
        if not g:
            g = {
                "batch_id": bid,
                "created_at": r.created_at,
                "total_ingresos": 0.0,
                "total_ganancia": 0.0,
                "total_items": 0,
                "min_hora": r.min_hora,
                "max_hora": r.max_hora,
            }
            grouped[bid] = g

        g["total_ingresos"] += float(r.ingresos or 0.0)
        g["total_ganancia"] += float(r.ganancia or 0.0)
        g["total_items"] += int(r.cantidad_total or 0)
        if r.min_hora and (g["min_hora"] is None or r.min_hora < g["min_hora"]):
            g["min_hora"] = r.min_hora
        if r.max_hora and (g["max_hora"] is None or r.max_hora > g["max_hora"]):
            g["max_hora"] = r.max_hora

    batches = list(grouped.values())
    batches.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return batches


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, db: Session = Depends(get_session)):
    """
    Detalle de un batch: devuelve los SalesArchiveSummary pertenecientes al batch_id.
    """
    rows = db.exec(
        select(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="batch not found")
    return rows


@router.get("/metrics")
def archive_metrics(period: str = Query("day", regex="^(day|week|month)$"), db: Session = Depends(get_session)):
    """
    Devuelve lista ordenada de { period, ingresos, ganancia, items } agrupada por day|week|month.
    period: "day" | "week" | "month"
    """
    rows = db.exec(select(SalesArchiveSummary)).all()
    if not rows:
        return []

    buckets = defaultdict(lambda: {"ingresos": 0.0, "ganancia": 0.0, "items": 0})
    for r in rows:
        ts = r.created_at or r.min_hora or datetime.utcnow()
        if period == "day":
            key = ts.strftime("%Y-%m-%d")
        elif period == "week":
            key = f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}"
        else:
            key = ts.strftime("%Y-%m")
        buckets[key]["ingresos"] += float(r.ingresos or 0.0)
        buckets[key]["ganancia"] += float(r.ganancia or 0.0)
        buckets[key]["items"] += int(r.cantidad_total or 0)

    result = []
    for k in sorted(buckets.keys()):
        result.append({
            "period": k,
            "ingresos": round(buckets[k]["ingresos"], 2),
            "ganancia": round(buckets[k]["ganancia"], 2),
            "items": int(buckets[k]["items"]),
        })
    return result


def _gen_period_keys(period: str, last: int) -> List[str]:
    """Genera keys para los últimos `last` periodos (asc order)"""
    keys: List[str] = []
    today = datetime.utcnow().date()
    if period == "day":
        for i in range(last - 1, -1, -1):
            d = today - timedelta(days=i)
            keys.append(d.strftime("%Y-%m-%d"))
    elif period == "week":
        # ISO week keys: YYYY-Www
        # compute starting week (today - (last-1) weeks)
        start_date = today - timedelta(weeks=last - 1)
        for i in range(last):
            d = start_date + timedelta(weeks=i)
            keys.append(f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}")
    else:
        # months
        year = today.year
        month = today.month
        # go back (last-1) months
        for i in range(last - 1, -1, -1):
            m = month - i
            y = year
            while m <= 0:
                m += 12
                y -= 1
            keys.append(f"{y}-{m:02d}")
    return keys


@router.get("/metrics/series")
def archive_metrics_series(
    period: str = Query("day", regex="^(day|week|month)$"),
    last: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_session),
):
    """
    Devuelve una serie con ceros incluidos para los últimos `last` periodos.
    Útil para gráficas (period: day|week|month).
    Respuesta: [{ period, ingresos, ganancia, items }, ...] (orden asc temporal)
    """
    raw = archive_metrics(period=period, db=db)  # reuse aggregation
    map_vals = {r["period"]: r for r in raw}
    keys = _gen_period_keys(period, last)
    series = []
    for k in keys:
        v = map_vals.get(k)
        if v:
            series.append(v)
        else:
            series.append({"period": k, "ingresos": 0.0, "ganancia": 0.0, "items": 0})
    return series


@router.get("/summary/totals")
def archive_totals(
    start: Optional[str] = Query(None, description="ISO date start (inclusive)"),
    end: Optional[str] = Query(None, description="ISO date end (inclusive)"),
    db: Session = Depends(get_session),
):
    """
    Totales agregados sobre SalesArchiveSummary.
    Si no se envían start/end devuelve totales globales.
    start/end deben ser ISO date or datetime strings parseable por datetime.fromisoformat.
    Respuesta: { ingresos, ganancia, items, batches }
    """
    try:
        rows = db.exec(select(SalesArchiveSummary)).all()
        if not rows:
            return {"ingresos": 0.0, "ganancia": 0.0, "items": 0, "batches": 0}

        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.fromisoformat(start)
        if end:
            end_dt = datetime.fromisoformat(end)

        ingresos = 0.0
        ganancia = 0.0
        items = 0
        batches_set = set()
        for r in rows:
            ts = r.created_at or r.min_hora or datetime.utcnow()
            if start_dt and ts < start_dt:
                continue
            if end_dt and ts > end_dt:
                continue
            ingresos += float(r.ingresos or 0.0)
            ganancia += float(r.ganancia or 0.0)
            items += int(r.cantidad_total or 0)
            if r.batch_id:
                batches_set.add(r.batch_id)

        return {
            "ingresos": round(ingresos, 2),
            "ganancia": round(ganancia, 2),
            "items": int(items),
            "batches": len(batches_set),
        }
    except Exception as exc:
        logger.error("archive_totals failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to compute totals")


@router.post("/run")
def run_archive(batch_size: int = Query(200, ge=1, le=10000)):
    """
    Ejecuta el worker de archivado. Archiva hasta `batch_size` ventas más recientes.
    """
    try:
        result = archive_batches_once(batch_size=batch_size)
    except Exception as exc:
        logger.error("archive run failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="archive run failed (ver logs del servidor)")

    if not result:
        return {"batch_id": None, "archived": 0, "message": "No sales archived"}

    batch_id, archived_count = result
    return {"batch_id": batch_id, "archived": archived_count}


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str, db: Session = Depends(get_session)):
    """
    Elimina todos los SalesArchiveSummary con batch_id dado.
    """
    try:
        stmt = select(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id)
        rows = db.exec(stmt).all()
        if not rows:
            raise HTTPException(status_code=404, detail="batch not found")
        # delete
        db.exec(delete(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id))
        db.commit()
        return {"deleted_batch_id": batch_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_batch failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="delete batch failed (ver logs del servidor)")


@router.delete("/batches")
def delete_all_summaries(confirm: bool = Query(False, description="Set true to confirm deletion"), db: Session = Depends(get_session)):
    """
    Elimina todos los SalesArchiveSummary. Requiere confirm=true para evitar borrados accidentales.
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm query param required to delete all summaries")

    try:
        db.exec(delete(SalesArchiveSummary))
        db.commit()
        return {"deleted_all": True, "message": "all summaries deleted"}
    except Exception as exc:
        logger.error("delete_all_summaries failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="delete all summaries failed (ver logs del servidor)")

from typing import List, Dict, Any, Optional
import logging
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel import Session

from ..database import get_session
from ..models import SalesArchiveSummary
from ..archive_worker import archive_batches_once

logger = logging.getLogger("archive_router")

router = APIRouter(prefix="/archive", tags=["archive"])


@router.get("/batches")
def list_batches(db: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """
    Lista batches agrupando los SalesArchiveSummary por batch_id.
    Devuelve: [{ batch_id, created_at, total_ingresos, total_ganancia, total_items, min_hora, max_hora }, ...]
    """
    rows = db.exec(select(SalesArchiveSummary)).all()
    if not rows:
        return []

    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        bid = r.batch_id
        g = grouped.get(bid)
        if not g:
            g = {
                "batch_id": bid,
                "created_at": r.created_at,
                "total_ingresos": 0.0,
                "total_ganancia": 0.0,
                "total_items": 0,
                "min_hora": r.min_hora,
                "max_hora": r.max_hora,
            }
            grouped[bid] = g

        g["total_ingresos"] += float(r.ingresos or 0.0)
        g["total_ganancia"] += float(r.ganancia or 0.0)
        g["total_items"] += int(r.cantidad_total or 0)
        if r.min_hora and (g["min_hora"] is None or r.min_hora < g["min_hora"]):
            g["min_hora"] = r.min_hora
        if r.max_hora and (g["max_hora"] is None or r.max_hora > g["max_hora"]):
            g["max_hora"] = r.max_hora

    batches = list(grouped.values())
    batches.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return batches


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, db: Session = Depends(get_session)):
    """
    Detalle de un batch: devuelve los SalesArchiveSummary pertenecientes al batch_id.
    """
    rows = db.exec(
        select(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="batch not found")
    return rows


@router.get("/metrics")
def archive_metrics(period: str = Query("day", regex="^(day|week|month)$"), db: Session = Depends(get_session)):
    """
    Devuelve lista ordenada de { period, ingresos, ganancia, items } agrupada por day|week|month.
    period: "day" | "week" | "month"
    """
    rows = db.exec(select(SalesArchiveSummary)).all()
    if not rows:
        return []

    buckets = defaultdict(lambda: {"ingresos": 0.0, "ganancia": 0.0, "items": 0})
    for r in rows:
        ts = r.created_at or r.min_hora or datetime.utcnow()
        if period == "day":
            key = ts.strftime("%Y-%m-%d")
        elif period == "week":
            key = f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}"
        else:
            key = ts.strftime("%Y-%m")
        buckets[key]["ingresos"] += float(r.ingresos or 0.0)
        buckets[key]["ganancia"] += float(r.ganancia or 0.0)
        buckets[key]["items"] += int(r.cantidad_total or 0)

    result = []
    for k in sorted(buckets.keys()):
        result.append({
            "period": k,
            "ingresos": round(buckets[k]["ingresos"], 2),
            "ganancia": round(buckets[k]["ganancia"], 2),
            "items": int(buckets[k]["items"]),
        })
    return result


def _gen_period_keys(period: str, last: int) -> List[str]:
    """Genera keys para los últimos `last` periodos (asc order)"""
    keys: List[str] = []
    today = datetime.utcnow().date()
    if period == "day":
        for i in range(last - 1, -1, -1):
            d = today - timedelta(days=i)
            keys.append(d.strftime("%Y-%m-%d"))
    elif period == "week":
        # ISO week keys: YYYY-Www
        # compute starting week (today - (last-1) weeks)
        start_date = today - timedelta(weeks=last - 1)
        for i in range(last):
            d = start_date + timedelta(weeks=i)
            keys.append(f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}")
    else:
        # months
        year = today.year
        month = today.month
        # go back (last-1) months
        for i in range(last - 1, -1, -1):
            m = month - i
            y = year
            while m <= 0:
                m += 12
                y -= 1
            keys.append(f"{y}-{m:02d}")
    return keys


@router.get("/metrics/series")
def archive_metrics_series(
    period: str = Query("day", regex="^(day|week|month)$"),
    last: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_session),
):
    """
    Devuelve una serie con ceros incluidos para los últimos `last` periodos.
    Útil para gráficas (period: day|week|month).
    Respuesta: [{ period, ingresos, ganancia, items }, ...] (orden asc temporal)
    """
    raw = archive_metrics(period=period, db=db)  # reuse aggregation
    map_vals = {r["period"]: r for r in raw}
    keys = _gen_period_keys(period, last)
    series = []
    for k in keys:
        v = map_vals.get(k)
        if v:
            series.append(v)
        else:
            series.append({"period": k, "ingresos": 0.0, "ganancia": 0.0, "items": 0})
    return series


@router.get("/summary/totals")
def archive_totals(
    start: Optional[str] = Query(None, description="ISO date start (inclusive)"),
    end: Optional[str] = Query(None, description="ISO date end (inclusive)"),
    db: Session = Depends(get_session),
):
    """
    Totales agregados sobre SalesArchiveSummary.
    Si no se envían start/end devuelve totales globales.
    start/end deben ser ISO date or datetime strings parseable por datetime.fromisoformat.
    Respuesta: { ingresos, ganancia, items, batches }
    """
    try:
        rows = db.exec(select(SalesArchiveSummary)).all()
        if not rows:
            return {"ingresos": 0.0, "ganancia": 0.0, "items": 0, "batches": 0}

        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.fromisoformat(start)
        if end:
            end_dt = datetime.fromisoformat(end)

        ingresos = 0.0
        ganancia = 0.0
        items = 0
        batches_set = set()
        for r in rows:
            ts = r.created_at or r.min_hora or datetime.utcnow()
            if start_dt and ts < start_dt:
                continue
            if end_dt and ts > end_dt:
                continue
            ingresos += float(r.ingresos or 0.0)
            ganancia += float(r.ganancia or 0.0)
            items += int(r.cantidad_total or 0)
            if r.batch_id:
                batches_set.add(r.batch_id)

        return {
            "ingresos": round(ingresos, 2),
            "ganancia": round(ganancia, 2),
            "items": int(items),
            "batches": len(batches_set),
        }
    except Exception as exc:
        logger.error("archive_totals failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to compute totals")


@router.post("/run")
def run_archive(batch_size: int = Query(200, ge=1, le=10000)):
    """
    Ejecuta el worker de archivado. Archiva hasta `batch_size` ventas más recientes.
    """
    try:
        result = archive_batches_once(batch_size=batch_size)
    except Exception as exc:
        logger.error("archive run failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="archive run failed (ver logs del servidor)")

    if not result:
        return {"batch_id": None, "archived": 0, "message": "No sales archived"}

    batch_id, archived_count = result
    return {"batch_id": batch_id, "archived": archived_count}


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str, db: Session = Depends(get_session)):
    """
    Elimina todos los SalesArchiveSummary con batch_id dado.
    """
    try:
        stmt = select(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id)
        rows = db.exec(stmt).all()
        if not rows:
            raise HTTPException(status_code=404, detail="batch not found")
        # delete
        db.exec(delete(SalesArchiveSummary).where(SalesArchiveSummary.batch_id == batch_id))
        db.commit()
        return {"deleted_batch_id": batch_id, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_batch failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="delete batch failed (ver logs del servidor)")


@router.delete("/batches")
def delete_all_summaries(confirm: bool = Query(False, description="Set true to confirm deletion"), db: Session = Depends(get_session)):
    """
    Elimina todos los SalesArchiveSummary. Requiere confirm=true para evitar borrados accidentales.
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm query param required to delete all summaries")

    try:
        db.exec(delete(SalesArchiveSummary))
        db.commit()
        return {"deleted_all": True, "message": "all summaries deleted"}
    except Exception as exc:
        logger.error("delete_all_summaries failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="delete all summaries failed (ver logs del servidor)")