from traceback import print_exc
from app.archive_worker import archive_batches_once

if __name__ == "__main__":
    try:
        print("Running archive_batches_once(batch_size=10) ...")
        res = archive_batches_once(batch_size=10)
        print("Result:", res)
    except Exception:
        print("Exception during local run:")
        print_exc()