from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
import json
import re

app = FastAPI()

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "processar-faturamento",
        "version": "2.0",
        "expected_columns": [
            "Cod. Cli./For.",
            "Cliente/Fornecedor",
            "Data",
            "Total Item",
            "Vendedor",
            "Ref. Produto",
            "Des. Grupo Completa",
            "Marca",
            "Cidade",
            "Estado"
        ]
    }

def normalizar_valor_brasileiro(valor_str: str) -> str:
    """
    Converte valores tipo:
      '4.189,00' -> '4189.00'
      '480,00'   -> '480.00'
      '502,50'   -> '502.50'
      '1.108,95' -> '1108.95'
      '35,00'    -> '35.00'
    """
    try:
        bruto = (valor_str or "").strip()
        # remove tudo que NÃO é dígito, ponto ou vírgula
        bruto = re.sub(r"[^\d.,-]", "", bruto)

        if bruto == "":
            return "0.00"

        # regra: último separador é decimal -> vírgula vira ponto
        # antes disso, todos os pontos são milhares
        # exemplo "4.189,00":
        #   tira os pontos -> "4189,00"
        #   troca vírgula -> "4189.00"
        sem_milhar = bruto.replace(".", "")
        decimal_ponto = sem_milhar.replace(",", ".")

        # valida float
        valor_float = float(decimal_ponto)

        # devolve com 2 casas fixas
        return f"{valor_float:.2f}"
    except Exception as e:
        print(f"❌ Erro conversão valor '{valor_str}': {e}")
        return "0.00"


@app.post("/processar-faturamento")
async def processar_faturamento(request: Request):
    """
    Recebe { "html_email": "<table>...</table>" }
    Retorna um array de objetos assim:
    [
      {
        "Cod. Cli./For.": "...",
        "Cliente/Fornecedor": "...",
        "Data": "DD/MM/YYYY",
        "Total Item": "1234.56",
        "Vendedor": "...",
        "Ref. Produto": "...",
        "Des. Grupo Completa": "...",
        "Marca": "...",
        "Cidade": "...",
        "Estado": "SC"
      },
      ...
    ]
    """
    try:
        raw_body = await request.body()
        raw_str = raw_body.decode("utf-8").strip()

        # tenta interpretar como JSON { "html_email": "<table>...</table>" }
        html = ""
        try:
            payload = json.loads(raw_str)
            html = payload.get("html_email", "")
        except Exception:
            # fallback: mandaram HTML puro no body
            html = raw_str

        if not html:
            print("⚠️ Nenhum HTML encontrado no corpo.")
            return []

        # limpa \r \n \t só pra evitar ruído
        html = re.sub(r"[\r\n\t]+", " ", html)

        soup = BeautifulSoup(html, "html.parser")
        linhas_processadas = []

        # percorre TODAS as linhas <tr>
        for tr in soup.find_all("tr"):
            classes = tr.get("class", []) or []

            # só pega linhas de dados (destaca / destacb)
            if not any("destac" in c for c in classes):
                continue

            tds = tr.find_all("td")
            qtd_cols = len(tds)

            # esperamos EXATAMENTE 10 colunas nesta ordem:
            # 0 Cod. Cli./For.
            # 1 Cliente/Fornecedor
            # 2 Data
            # 3 Total Item
            # 4 Vendedor
            # 5 Ref.Produto
            # 6 Des. Grupo Completa
            # 7 Marca
            # 8 Cidade
            # 9 Estado
            if qtd_cols < 10:
                print(f"⚠️ Ignorando linha: {qtd_cols} colunas (esperado >=10)")
                # debug rápido:
                for idx, td in enumerate(tds):
                    print(f"   col[{idx}]: {td.get_text(strip=True)}")
                continue

            try:
                cod_cli_for       = tds[0].get_text(strip=True)
                cliente_fornecedor= tds[1].get_text(strip=True)
                data_str          = tds[2].get_text(strip=True)
                total_bruto       = tds[3].get_text(strip=True)
                vendedor          = tds[4].get_text(strip=True)
                ref_produto       = tds[5].get_text(strip=True)
                desc_grupo        = tds[6].get_text(strip=True)
                marca             = tds[7].get_text(strip=True)
                cidade            = tds[8].get_text(strip=True)
                estado            = tds[9].get_text(strip=True)

                total_norm = normalizar_valor_brasileiro(total_bruto)

                registro = {
                    "Cod. Cli./For.": cod_cli_for,
                    "Cliente/Fornecedor": cliente_fornecedor,
                    "Data": data_str,
                    "Total Item": total_norm,
                    "Vendedor": vendedor,
                    "Ref. Produto": ref_produto,
                    "Des. Grupo Completa": desc_grupo,
                    "Marca": marca,
                    "Cidade": cidade,
                    "Estado": estado
                }

                linhas_processadas.append(registro)

                print(
                    f"✅ Faturamento linha OK | {cliente_fornecedor[:30]} | R$ {total_norm} | {vendedor[:30]}"
                )

            except Exception as e:
                print(f"⚠️ Erro ao montar registro: {e}")
                for idx, td in enumerate(tds):
                    print(f"   DBG col[{idx}]: {td.get_text(strip=True)}")
                continue

        print(f"📦 Total linhas faturamento extraídas: {len(linhas_processadas)}")
        return linhas_processadas

    except Exception as e:
        print(f"❌ Erro geral no /processar-faturamento: {e}")
        import traceback
        traceback.print_exc()
        return []
