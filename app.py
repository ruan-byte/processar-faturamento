from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
import json
import re

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "online", "service": "processar-faturamento", "version": "1.1"}


def converter_valor_brasileiro(valor_str: str) -> str:
    """
    Converte valores no formato brasileiro para decimal padrão.
    Ex: "1.250,50" → "1250.50"
    """
    try:
        valor_limpo = valor_str.strip()
        valor_limpo = re.sub(r"[^\d,.-]", "", valor_limpo)

        if not valor_limpo:
            return "0.00"

        if "," in valor_limpo:
            valor_sem_pontos = valor_limpo.replace(".", "")
            valor_final = valor_sem_pontos.replace(",", ".")
        else:
            partes = valor_limpo.split(".")
            if len(partes) == 2 and len(partes[1]) <= 2:
                valor_final = valor_limpo
            else:
                valor_final = valor_limpo.replace(".", "")

        return "{:.2f}".format(float(valor_final))

    except Exception as e:
        print(f"❌ Erro ao converter '{valor_str}': {e}")
        return "0.00"


@app.post("/processar-faturamento")
async def processar_faturamento(request: Request):
    """
    Processa o HTML do e-mail de faturamento e devolve JSON formatado.
    Compatível com a nova estrutura (10 colunas) do e-mail.
    """
    try:
        body = await request.body()
        body_str = body.decode("utf-8").strip()

        try:
            payload = json.loads(body_str)
            html = payload.get("html_email", "")
        except:
            html = body_str

        if not html:
            return []

        # Limpar e preparar HTML
        html = re.sub(r"[\r\n\t]+", " ", html)
        soup = BeautifulSoup(html, "html.parser")

        faturamento = []

        for tr in soup.find_all("tr"):
            classes = tr.get("class", []) or []
            if not any("destac" in str(c) for c in classes):
                continue

            cells = tr.find_all("td")
            if len(cells) < 10:
                print(f"⚠️ Linha ignorada ({len(cells)} colunas, esperado ≥ 10)")
                continue

            try:
                cod_cli_for = cells[0].get_text(strip=True)
                cliente = cells[1].get_text(strip=True)
                data = cells[2].get_text(strip=True)
                total_str = cells[3].get_text(strip=True)
                vendedor = cells[4].get_text(strip=True)
                ref_produto = cells[5].get_text(strip=True)
                grupo = cells[6].get_text(strip=True)
                marca = cells[7].get_text(strip=True)
                cidade = cells[8].get_text(strip=True)
                estado = cells[9].get_text(strip=True)

                total = converter_valor_brasileiro(total_str)

                if not cliente or not total:
                    continue

                item = {
                    "Cod. Cli./For.": cod_cli_for,
                    "Cliente/Fornecedor": cliente,
                    "Data": data,
                    "Total Item": total,
                    "Vendedor": vendedor,
                    "Ref. Produto": ref_produto,
                    "Des. Grupo Completa": grupo,
                    "Marca": marca,
                    "Cidade": cidade,
                    "Estado": estado
                }

                faturamento.append(item)
                print(f"💰 {cliente[:30]}... | R$ {total} | {vendedor[:25]}")

            except Exception as e:
                print(f"⚠️ Erro ao processar linha: {e}")
                for i, td in enumerate(cells[:10]):
                    print(f"   cells[{i}] = {td.get_text(strip=True)}")
                continue

        print(f"📦 Total processado: {len(faturamento)} registros")
        return faturamento

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return []
