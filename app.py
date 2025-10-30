from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import json
import re

app = FastAPI(title="Processar Faturamento API", version="5.0-FINAL")

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
        "version": "5.0-FINAL",
        "note": "Retorna array direto com JSON limpo e validado",
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

def clean_json_value(value):
    """
    Remove caracteres problemáticos que quebram JSON.
    - Quebras de linha
    - Tabs
    - Múltiplos espaços
    - Caracteres de controle
    """
    if value is None:
        return ""
    
    value_str = str(value).strip()
    
    # Remove quebras de linha e retorno de carro
    value_str = value_str.replace('\n', ' ').replace('\r', ' ')
    
    # Remove tabs
    value_str = value_str.replace('\t', ' ')
    
    # Remove caracteres de controle Unicode
    value_str = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', value_str)
    
    # Remove múltiplos espaços
    value_str = ' '.join(value_str.split())
    
    return value_str


def converter_valor_brasileiro(valor_str: str) -> str:
    """
    Converte valores do formato brasileiro para formato numérico.
    Exemplos:
    - "18.629,20" -> "18629.20"
    - "9.455,00" -> "9455.00"
    - "373,50" -> "373.50"
    - "1.620,00" -> "1620.00"
    """
    try:
        # Remove espaços
        valor_limpo = valor_str.strip()
        
        # Remove qualquer caractere que não seja número, ponto ou vírgula
        valor_limpo = re.sub(r'[^\d,.]', '', valor_limpo)
        
        if not valor_limpo:
            return "0"
        
        # Se tem vírgula, é formato brasileiro
        if ',' in valor_limpo:
            # Remove pontos (separador de milhar)
            valor_sem_pontos = valor_limpo.replace('.', '')
            # Troca vírgula por ponto (decimal)
            valor_final = valor_sem_pontos.replace(',', '.')
        else:
            # Não tem vírgula, só ponto
            partes = valor_limpo.split('.')
            
            if len(partes) == 2 and len(partes[1]) == 2:
                # Provavelmente decimal: "373.50"
                valor_final = valor_limpo
            else:
                # Provavelmente milhar: "1.234" -> "1234"
                valor_final = valor_limpo.replace('.', '')
        
        # Valida se é um número válido
        float(valor_final)
        
        return valor_final
        
    except Exception as e:
        print(f"❌ Erro ao converter valor '{valor_str}': {e}")
        return "0"


@app.post("/processar-faturamento")
async def processar_faturamento(request: Request):
    """
    IMPORTANTE: Retorna array DIRETO (sem wrapper "data")
    JSON limpo e validado, sem caracteres que quebram parsing
    
    Input:
    {
      "html_email": "<table>...</table>"
    }
    
    Output (array direto):
    [
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
    """
    try:
        body = await request.body()
        body_str = body.decode("utf-8").strip()

        print(f"📥 Recebido request - Tamanho: {len(body_str)} chars")

        # Tenta interpretar como JSON
        try:
            payload = json.loads(body_str)
            html = payload.get("html_email", "")
            print("✅ JSON parseado com sucesso")
        except:
            html = body_str
            print("⚠️ Não é JSON válido, tratando como HTML puro")

        if not html:
            print("❌ HTML vazio")
            return []

        # Limpa caracteres de controle
        html = re.sub(r"[\r\n\t]+", " ", html)
        
        soup = BeautifulSoup(html, "html.parser")
        faturamento = []

        # Processa linhas com classe "destaca" ou "destacb"
        for tr in soup.find_all("tr"):
            classes = tr.get("class", []) or []
            if not any("destac" in str(c) for c in classes):
                continue

            cells = tr.find_all("td")
            
            print(f"📊 Linha com {len(cells)} células")
            
            # ✅ ESTRUTURA DO FATURAMENTO (baseada no código original)
            # cells[0]  = Cod. Cli./For.
            # cells[1]  = Cliente/Fornecedor
            # cells[2]  = Data
            # cells[5]  = Ref. Produto
            # cells[7]  = Des. Grupo Completa
            # cells[9]  = Total Item
            # cells[11] = Vendedor
            # cells[12] = Marca
            # cells[13] = Cidade
            # cells[14] = Estado
            
            if len(cells) < 16:
                print(f"⚠️ Linha ignorada: só tem {len(cells)} células (esperado >= 16)")
                continue

            try:
                # ✅ EXTRAI E LIMPA CADA CAMPO
                cod_cli_for = clean_json_value(cells[0].get_text(strip=True))
                cliente = clean_json_value(cells[1].get_text(strip=True))
                data = clean_json_value(cells[2].get_text(strip=True))
                ref_produto = clean_json_value(cells[5].get_text(strip=True))
                grupo = clean_json_value(cells[7].get_text(strip=True))
                total_str = clean_json_value(cells[9].get_text(strip=True))
                vendedor = clean_json_value(cells[11].get_text(strip=True))
                marca = clean_json_value(cells[12].get_text(strip=True))
                cidade = clean_json_value(cells[13].get_text(strip=True))
                estado = clean_json_value(cells[14].get_text(strip=True))

                # Converte valor
                total = converter_valor_brasileiro(total_str)

                # Validação básica
                if not cliente or cliente == "":
                    cliente = f"CLIENTE_{cod_cli_for}"
                    print(f"⚠️ Cliente vazio, usando fallback: {cliente}")

                if not total or total == "0":
                    print(f"⚠️ Registro ignorado: Total zerado ou inválido")
                    continue

                # ✅ MONTA OBJETO COM VALORES LIMPOS
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

                print(f"💰 {cliente[:35]}... | R$ {total} | {vendedor[:30]}")

            except Exception as e:
                print(f"⚠️ Erro ao processar linha: {e}")
                # Debug: mostra células
                for i in range(min(len(cells), 16)):
                    print(f"   cells[{i}] = {cells[i].get_text(strip=True)[:50]}")
                continue

        print(f"📦 Total processado: {len(faturamento)} registros de faturamento")
        
        # ✅ VALIDA JSON ANTES DE RETORNAR
        try:
            # Tenta serializar para garantir que é JSON válido
            json_test = json.dumps(faturamento)
            print(f"✅ JSON validado com sucesso - {len(json_test)} bytes")
        except Exception as e:
            print(f"❌ ERRO: JSON inválido gerado! {e}")
            return []
        
        # ✅ RETORNA ARRAY DIRETO (sem wrapper "data")
        return faturamento

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return []


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "processar-faturamento"}
