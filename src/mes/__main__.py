"""Start a mini MES.

Usage:  python -m src.mes                              (temporary database, free port)
        python -m src.mes --port 8080 --defects DEF-03  (to look at it in a browser)
        python -m src.mes --run-id <id> --db <file> --defects DEF-01,DEF-03   (used by the harness)

The process binds its own port (port 0 = let the system choose a free one) and,
once it listens, prints one JSON line to standard output:
    {"ready": true, "port": 51234, "run_id": "...", "url": "http://127.0.0.1:51234"}
"""

import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path

import uvicorn

from src.mes.app import create_app
from src.mes.defects import DefectError, parse_defects
from src.mes.seed import build_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.mes", description="Start the mini MES.")
    parser.add_argument("--run-id", default="manual", help="identity reported by /health")
    parser.add_argument("--db", help="SQLite file; built from the data files if it does not exist")
    parser.add_argument("--defects", default="", help="comma-separated defect ids, e.g. DEF-01,DEF-03")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 lets the system pick a free port")
    args = parser.parse_args(argv)

    try:
        defects = parse_defects(args.defects)
    except DefectError as error:
        print(error, file=sys.stderr)
        return 2

    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            build_database(db_path)
    else:
        db_path = build_database(Path(tempfile.mkdtemp(prefix="mini-mes-")) / "mes.db")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((args.host, args.port))
    sock.listen(128)
    port = sock.getsockname()[1]

    app = create_app(db_path, defects, args.run_id)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    # The socket already listens, so a client that connects now is served as soon as the loop runs.
    print(json.dumps({"ready": True, "port": port, "run_id": args.run_id, "url": f"http://{args.host}:{port}"}), flush=True)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
