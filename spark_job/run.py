"""Entry point submitted to spark-submit. Kept as a thin top-level script
(sibling of the spark_job/ package, not inside it) so spark_job's internal
modules can use ordinary relative imports (from .config import ...) - running
spark_job/main.py directly as the submitted script would execute it as
__main__ outside of any package context, breaking those relative imports.
"""
from spark_job.main import main

if __name__ == "__main__":
    main()
