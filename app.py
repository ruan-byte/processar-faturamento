from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import json
import re

app = FastAPI(title="Processar Faturamento API", version="6.0-FIXED")

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
        "version": "6.0-FIXED",
        "note": "Versão corrigida para estrutura HTML com 10 colunas",
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
    PRESERVA valores negativos (devoluções).
    Exemplos:
    - "18.629,20" -> "18629.20"
    - "-1.040,00" -> "-1040.00" (mantém negativo para devoluções)
    - "373,50" -> "373.50"
    """
    try:
        # Remove espaços
        valor_limpo = valor_str.strip()
        
        # Verifica se é negativo
        is_negative = valor_limpo.startswith('-')
        
        # Remove sinal temporariamente para processar
        if is_negative:
            valor_limpo = valor_limpo[1:]
        
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
        
        # Restaura o sinal negativo se necessário
        if is_negative:
            valor_final = '-' + valor_final
        
        # Valida se é um número válido
        float(valor_final)
        
        return valor_final
        
    except Exception as e:
        print(f"❌ Erro ao converter valor '{valor_str}': {e}")
        return "0"


@app.post("/processar-faturamento")
async def processar_faturamento(request: Request):
    """
    Processa HTML de faturamento e retorna array JSON.
    
    Estrutura do HTML:
    - 10 colunas visíveis na tabela
    - Células com índices 0-9
    
    Mapeamento correto das colunas:
    - cells[0] = Cod. Cli./For.
    - cells[1] = Cliente/Fornecedor
    - cells[2] = Data
    - cells[3] = Total Item
    - cells[4] = Vendedor
    - cells[5] = Ref. Produto
    - cells[6] = Des. Grupo Completa
    - cells[7] = Marca
    - cells[8] = Cidade
    - cells[9] = Estado
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

        # Debug: vamos verificar a estrutura primeiro
        sample_row = soup.find("tr", {"class": ["destaca", "destacb"]})
        if sample_row:
            sample_cells = sample_row.find_all("td")
            print(f"📊 Debug: Linha exemplo tem {len(sample_cells)} células")
            if len(sample_cells) >= 10:
                for i in range(10):
                    print(f"   Cell[{i}]: {sample_cells[i].get_text(strip=True)[:50]}")

        # Processa linhas com classe "destaca" ou "destacb"
        for tr in soup.find_all("tr"):
            # Verifica se tem uma das classes
            tr_class = tr.get("class", [])
            if not tr_class:
                continue
            
            # Converte para string se for lista
            class_str = " ".join(tr_class) if isinstance(tr_class, list) else str(tr_class)
            
            # Verifica se é uma linha de dados
            if "destaca" not in class_str and "destacb" not in class_str:
                continue

            cells = tr.find_all("td")
            
            # HTML tem exatamente 10 colunas
            if len(cells) < 10:
                print(f"⚠️ Linha ignorada: só tem {len(cells)} células (esperado 10)")
                continue

            try:
                # ✅ EXTRAI E LIMPA CADA CAMPO (índices 0-9)
                cod_cli_for = clean_json_value(cells[0].get_text(strip=True))
                cliente = clean_json_value(cells[1].get_text(strip=True))
                data = clean_json_value(cells[2].get_text(strip=True))
                total_str = clean_json_value(cells[3].get_text(strip=True))
                vendedor = clean_json_value(cells[4].get_text(strip=True))
                ref_produto = clean_json_value(cells[5].get_text(strip=True))
                grupo = clean_json_value(cells[6].get_text(strip=True))
                marca = clean_json_value(cells[7].get_text(strip=True))
                cidade = clean_json_value(cells[8].get_text(strip=True))
                estado = clean_json_value(cells[9].get_text(strip=True))

                # Converte valor (preserva sinal negativo se for devolução)
                total = converter_valor_brasileiro(total_str)

                # Validação básica
                if not cliente or cliente == "":
                    # Se cliente está vazio, pula este registro
                    print(f"⚠️ Registro ignorado: Cliente vazio")
                    continue

                # Aceita valores negativos (devoluções) e positivos
                if total == "0":
                    print(f"⚠️ Registro ignorado: Total zerado")
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

                print(f"✅ {cliente[:30]}... | R$ {total} | {vendedor[:25]}...")

            except Exception as e:
                print(f"⚠️ Erro ao processar linha: {e}")
                continue

        print(f"📦 Total processado: {len(faturamento)} registros de faturamento")
        
        # ✅ VALIDA JSON ANTES DE RETORNAR
        try:
            # Tenta serializar para garantir que é JSON válido
            json_test = json.dumps(faturamento, ensure_ascii=False)
            print(f"✅ JSON validado com sucesso - {len(json_test)} bytes")
        except Exception as e:
            print(f"❌ ERRO: JSON inválido gerado! {e}")
            return []
        
        # ✅ RETORNA ARRAY DIRETO
        return faturamento

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return []


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "processar-faturamento", "version": "6.0-FIXED"}
