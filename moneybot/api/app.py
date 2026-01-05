from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="MoneyBot")


@app.get("/", include_in_schema=False)
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/ui", response_class=HTMLResponse)
def ui_placeholder() -> str:
    return """
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>MoneyBot UI</title>
      </head>
      <body>
        <h1>MoneyBot UI</h1>
        <p>La interfaz web estará disponible aquí.</p>
      </body>
    </html>
    """
