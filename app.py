from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import json
import re

app = FastAPI(title="Processar Faturamento API", version="2.0")

# CORS para permitir chamadas do Make.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        ],
        "endpoints": {
            "POST /processar-faturamento": "Processa HTML de email de faturamento"
        }
    }

def normalizar_valor_brasileiro(valor_str: str) -> str:
    """
    Converte valores brasileiros para formato numérico:
      '4.189,00' -> '4189.00'
      '480,00'   -> '480.00'
      '1.108,95' -> '1108.95'
    """
    try:
        bruto = (valor_str or "").strip()
        # Remove caracteres inválidos (mantém apenas dígitos, ponto, vírgula e hífen)
        bruto = re.sub(r"[^\d.,-]", "", bruto)

        if bruto == "":
            return "0.00"

        # Remove pontos de milhar e substitui vírgula decimal por ponto
        sem_milhar = bruto.replace(".", "")
        decimal_ponto = sem_milhar.replace(",", ".")

        # Valida e formata
        valor_float = float(decimal_ponto)
        return f"{abs(valor_float):.2f}"
    except Exception as e:
        print(f"❌ Erro ao converter valor '{valor_str}': {e}")
        return "0.00"


@app.post("/processar-faturamento")
async def processar_faturamento(request: Request):
    """
    Recebe HTML de email com tabela de faturamento e retorna JSON estruturado.
    
    Input:
    {
      "html_email": "<table>...</table>"
    }
    
    Output:
    {
      "data": [
        {
          "Cod. Cli./For.": "2803",
          "Cliente/Fornecedor": "AURORA ABATE DE AVES",
          "Data": "01/10/2025",
          "Total Item": "480.00",
          "Vendedor": "259 - SABRINA E LISI (OESTE)",
          "Ref. Produto": "AMS-5P-00/M12-F-90G",
          "Des. Grupo Completa": "CONECTOR M12 ANGULAR...",
          "Marca": "ASITECH",
          "Cidade": "GUATAMBU",
          "Estado": "SC"
        }
      ]
    }
    """
    try:
        # Lê o body da requisição
        raw_body = await request.body()
        raw_str = raw_body.decode("utf-8").strip()

        print(f"📥 Recebido request - Tamanho: {len(raw_str)} chars")

        # Tenta interpretar como JSON
        html = ""
        try:
            payload = json.loads(raw_str)
            html = payload.get("html_email", "")
            print("✅ JSON parseado com sucesso")
        except Exception as e:
            # Fallback: HTML puro no body
            html = raw_str
            print(f"⚠️ Não é JSON válido, tratando como HTML puro: {e}")

        if not html or len(html) < 10:
            print("❌ Nenhum HTML válido encontrado")
            return {"data": [], "error": "HTML vazio ou inválido"}

        # Limpa caracteres de controle
        html = re.sub(r"[\r\n\t]+", " ", html)
        
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")
        linhas_processadas = []

        # Procura por tabela
        tabela = soup.find("table")
        if not tabela:
            print("⚠️ Nenhuma tabela encontrada no HTML")
            return {"data": [], "error": "Nenhuma tabela encontrada"}

        # Processa linhas da tabela
        linhas_tr = tabela.find_all("tr")
        print(f"📊 Encontradas {len(linhas_tr)} linhas na tabela")

        for idx, tr in enumerate(linhas_tr):
            # Pula cabeçalho (primeira linha geralmente)
            if idx == 0:
                colunas_header = [th.get_text(strip=True) for th in tr.find_all(["th", "td"])]
                print(f"📋 Cabeçalho: {colunas_header}")
                continue

            tds = tr.find_all("td")
            qtd_cols = len(tds)

            # Valida quantidade de colunas (esperamos 10)
            if qtd_cols < 10:
                print(f"⚠️ Linha {idx}: {qtd_cols} colunas (esperado 10)")
                continue

            try:
                # Extrai valores de cada coluna
                cod_cli_for        = tds[0].get_text(strip=True)
                cliente_fornecedor = tds[1].get_text(strip=True)
                data_str           = tds[2].get_text(strip=True)
                total_bruto        = tds[3].get_text(strip=True)
                vendedor           = tds[4].get_text(strip=True)
                ref_produto        = tds[5].get_text(strip=True)
                desc_grupo         = tds[6].get_text(strip=True)
                marca              = tds[7].get_text(strip=True)
                cidade             = tds[8].get_text(strip=True)
                estado             = tds[9].get_text(strip=True)

                # Normaliza valor
                total_norm = normalizar_valor_brasileiro(total_bruto)

                # Monta registro
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

                # Log a cada 100 registros
                if len(linhas_processadas) % 100 == 0:
                    print(f"📦 Processados {len(linhas_processadas)} registros...")

            except Exception as e:
                print(f"❌ Erro ao processar linha {idx}: {e}")
                continue

        print(f"✅ Total de registros processados: {len(linhas_processadas)}")

        # Retorna no formato esperado pela Edge Function
        return {
            "data": linhas_processadas,
            "total_registros": len(linhas_processadas),
            "timestamp": None  # Make.com vai adicionar
        }

    except Exception as e:
        print(f"❌ Erro geral no /processar-faturamento: {e}")
        import traceback
        traceback.print_exc()
        return {
            "data": [],
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "processar-faturamento"}
