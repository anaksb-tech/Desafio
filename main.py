from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def calcular_cashback(tipo_cliente: str, valor_compra: float, desconto_percentual: float) -> dict:
    valor_final = valor_compra * (1 - desconto_percentual / 100)

    cashback_base = valor_final * 0.05

    dobrou = valor_final > 500
    if dobrou:
        cashback_base *= 2

    cashback_final = cashback_base
    bonus_vip = 0.0

    if tipo_cliente.upper() == "VIP":
        bonus_vip = cashback_base * 0.10
        cashback_final = cashback_base + bonus_vip

    return {
        "valor_original": valor_compra,
        "desconto_percentual": desconto_percentual,
        "valor_final": round(valor_final, 2),
        "cashback_base_bruto": round(cashback_base, 2),
        "dobrou": dobrou,
        "cliente_vip": tipo_cliente.upper() == "VIP",
        "bonus_vip": round(bonus_vip, 2),
        "cashback_final": round(cashback_final, 2),
    }


class CompraRequest(BaseModel):
    tipo_cliente: str      
    valor_compra: float
    desconto_percentual: float = 0.0


@app.post("/api/calcular")
async def api_calcular(compra: CompraRequest, request: Request):
    resultado = calcular_cashback(
        compra.tipo_cliente,
        compra.valor_compra,
        compra.desconto_percentual,
    )

    ip = request.headers.get("x-forwarded-for", request.client.host)
    ip = ip.split(",")[0].strip()

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO historico_consultas (ip_usuario, tipo_cliente, valor_compra, valor_cashback)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (ip, compra.tipo_cliente.upper(), compra.valor_compra, resultado["cashback_final"]),
                )
    finally:
        conn.close()

    return {"ip": ip, "calculo": resultado}


@app.get("/api/historico")
async def api_historico(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host)
    ip = ip.split(",")[0].strip()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tipo_cliente, valor_compra, valor_cashback, data_consulta
                FROM historico_consultas
                WHERE ip_usuario = %s
                ORDER BY data_consulta DESC
                """,
                (ip,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "tipo_cliente": r[0],
            "valor_compra": float(r[1]),
            "cashback": float(r[2]),
            "data_consulta": r[3].isoformat(),
        }
        for r in rows
    ]


@app.get("/")
def root():
    return {"status": "ok", "message": "API de Cashback Nology"}
