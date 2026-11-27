"""Web pages and read-only API of the mini MES (design section 6.1).

Pages are rendered on the server and use plain, labelled HTML. Elements also carry
`id` and `data-testid` attributes for the baseline scripts and the oracle; the agent
never sees those.
"""

from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.mes.db import connect
from src.mes.service import MesService

HERE = Path(__file__).resolve().parent


def _parse_qty(raw: str | None) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def create_app(db_path: Path | str, defects: frozenset[str] = frozenset(), run_id: str = "manual") -> FastAPI:
    app = FastAPI(title="Mini MES", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def service() -> Iterator[MesService]:
        conn = connect(db_path)
        try:
            yield MesService(conn, defects)
        finally:
            conn.close()

    def page(request: Request, name: str, **context) -> HTMLResponse:
        return templates.TemplateResponse(request, name, context)

    def not_found(what: str):
        raise HTTPException(status_code=404, detail=f"{what} not found")

    # ---- pages -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "home.html", active="home")

    @app.get("/inventory", response_class=HTMLResponse)
    def inventory(request: Request, q: str = "", mes: MesService = Depends(service)):
        return page(request, "inventory.html", active="inventory", parts=mes.list_parts(q), q=q)

    @app.get("/parts/{part_id}", response_class=HTMLResponse)
    def part_detail(request: Request, part_id: str, mes: MesService = Depends(service)):
        part = mes.get_part(part_id) or not_found("Part")
        return page(request, "part.html", active="inventory", part=part, movements=mes.list_movements(part_id=part_id)[:10])

    @app.get("/work-orders", response_class=HTMLResponse)
    def work_orders(request: Request, mes: MesService = Depends(service)):
        return page(request, "work_orders.html", active="work_orders", work_orders=mes.list_work_orders())

    @app.get("/work-orders/{work_order_id}", response_class=HTMLResponse)
    def work_order_detail(request: Request, work_order_id: str, mes: MesService = Depends(service)):
        work_order = mes.get_work_order(work_order_id) or not_found("Work order")
        return page(request, "work_order.html", active="work_orders", work_order=work_order,
                    movements=mes.list_movements(work_order_id=work_order_id))

    @app.get("/issue", response_class=HTMLResponse)
    def issue_form(request: Request, part: str = "", work_order: str = "", mes: MesService = Depends(service)):
        open_orders = [wo for wo in mes.list_work_orders() if wo["status"] == "OPEN"]
        return page(request, "issue_form.html", active="issue", parts=mes.list_parts(), work_orders=open_orders,
                    selected_part=part, selected_work_order=work_order)

    @app.post("/issue")
    def issue_submit(
        work_order_id: str = Form(""),
        part_id: str = Form(""),
        qty: str = Form(""),
        mes: MesService = Depends(service),
    ):
        result = mes.issue_part(part_id.strip(), work_order_id.strip(), _parse_qty(qty))
        return RedirectResponse(f"/issue/result/{result.request_id}", status_code=303)

    @app.get("/issue/result/{request_id}", response_class=HTMLResponse)
    def issue_result(request: Request, request_id: int, mes: MesService = Depends(service)):
        issue = mes.get_issue_request(request_id) or not_found("Issue request")
        return page(request, "issue_result.html", active="issue", issue=issue)

    @app.get("/movements", response_class=HTMLResponse)
    def movements(request: Request, mes: MesService = Depends(service)):
        return page(request, "movements.html", active="movements", movements=mes.list_movements())

    # ---- read-only API ---------------------------------------------------

    @app.get("/api/parts")
    def api_parts(mes: MesService = Depends(service)):
        return mes.list_parts()

    @app.get("/api/parts/{part_id}")
    def api_part(part_id: str, mes: MesService = Depends(service)):
        return mes.get_part(part_id) or not_found("Part")

    @app.get("/api/work-orders/{work_order_id}")
    def api_work_order(work_order_id: str, mes: MesService = Depends(service)):
        return mes.get_work_order(work_order_id) or not_found("Work order")

    @app.get("/api/movements")
    def api_movements(mes: MesService = Depends(service)):
        return mes.list_movements()

    @app.get("/api/issue-requests")
    def api_issue_requests(mes: MesService = Depends(service)):
        return mes.list_issue_requests()

    @app.get("/health")
    def health():
        return {"status": "ok", "run_id": run_id, "defects": sorted(defects)}

    return app
