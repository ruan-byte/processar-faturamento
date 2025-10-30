from fastapi import FastAPI, Request
from bs4 import BeautifulSoup
import json
import re

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "online", "version": "5.0"}

def converter_valor_brasileiro(valor_str: str) -> str:
    """
    Converte valores do formato brasileiro para formato numérico.
    ⚠️ PRESERVA VALORES NEGATIVOS (devoluções)
    
    Exemplos:
    - "18.629,20" -> "18629.20"
    - "-1.040,00" -> "-1040.00" ✅ (devolução)
    - "9.455,00" -> "9455.00"
    - "373,50" -> "373.50"
    - "1.620,00" -> "1620.00"
    """
    try:
        # Remove espaços
        valor_limpo = valor_str.strip()
        
        # ✅ Verifica se é negativo (DEVOLUÇÃO)
        is_negative = valor_limpo.startswith('-')
        if is_negative:
            valor_limpo = valor_limpo[1:].strip()  # Remove o sinal temporariamente
        
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
        
        # ✅ Restaura o sinal negativo se for devolução
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
    Processa HTML de email de faturamento e retorna array de objetos.
    
    ⚠️ ATENÇÃO: O HTML tem tags <tr> malformadas (não fechadas).
    Usa html5lib parser que é mais tolerante.
    
    ESTRUTURA ESPERADA DA TABELA (10 colunas):
    cells[0]  = Cod. Cli./For.
    cells[1]  = Cliente/Fornecedor
    cells[2]  = Data
    cells[3]  = Total Item
    cells[4]  = Vendedor
    cells[5]  = Ref. Produto
    cells[6]  = Des. Grupo Completa
    cells[7]  = Marca
    cells[8]  = Cidade
    cells[9]  = Estado
    
    Retorna:
    [
      {
        "Cod. Cli./For.": "642",
        "Cliente/Fornecedor": "METALBO",
        "Data": "30/10/2025",
        "Total Item": "3740.00",
        "Vendedor": "21 - CAMILY E PADILHA (VALE)",
        "Ref. Produto": "42M2N032A0100",
        "Des. Grupo Completa": "CIL. Ø32X100 D. ACAO D. AMORT. MAG.",
        "Marca": "CAMOZZI",
        "Cidade": "TROMBUDO CENTRAL",
        "Estado": "SC"
      }
    ]
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
            print("❌ HTML vazio!")
            return []

        print(f"📥 HTML recebido: {len(html)} caracteres")
        
        # ✅ USA html5lib PARA PARSEAR HTML MALFORMADO
        try:
            soup = BeautifulSoup(html, 'html5lib')
        except:
            print("⚠️ html5lib não disponível, usando html.parser")
            soup = BeautifulSoup(html, 'html.parser')
        
        faturamento = []
        linhas_processadas = 0
        linhas_ignoradas = 0
        devolucoes = 0
        
        print("🔍 Procurando linhas com classe 'destaca' ou 'destacb'...")

        for tr in soup.find_all("tr"):
            classes = tr.get("class", []) or []
            
            # Verifica se tem classe de faturamento
            if not any("destac" in str(c) for c in classes):
                continue

            cells = tr.find_all("td")
            linhas_processadas += 1
            
            print(f"\n📋 Processando linha {linhas_processadas} com {len(cells)} células")
            
            # ✅ Validação: deve ter exatamente 10 colunas
            if len(cells) != 10:
                print(f"⚠️ Linha {linhas_processadas} ignorada: tem {len(cells)} células (esperado 10)")
                linhas_ignoradas += 1
                
                # 🐛 DEBUG: Mostra o conteúdo para diagnóstico
                if len(cells) > 0:
                    for i in range(min(len(cells), 10)):
                        texto = cells[i].get_text(strip=True)[:60]
                        print(f"   cells[{i}] = {texto}")
                
                continue

            try:
                # ✅ EXTRAÇÃO COM ÍNDICES CORRETOS (10 colunas)
                cod_cli_for = cells[0].get_text(strip=True)      # Cod. Cli./For.
                cliente = cells[1].get_text(strip=True)          # Cliente/Fornecedor
                data = cells[2].get_text(strip=True)             # Data
                total_str = cells[3].get_text(strip=True)        # Total Item
                vendedor = cells[4].get_text(strip=True)         # Vendedor
                ref_produto = cells[5].get_text(strip=True)      # Ref. Produto
                grupo = cells[6].get_text(strip=True)            # Des. Grupo Completa
                marca = cells[7].get_text(strip=True)            # Marca
                cidade = cells[8].get_text(strip=True)           # Cidade
                estado = cells[9].get_text(strip=True)           # Estado
                
                print(f"   Cliente: {cliente[:40]}...")
                print(f"   Total (raw): {total_str}")
                
                # ✅ Converte o valor (PRESERVA SINAL NEGATIVO)
                total = converter_valor_brasileiro(total_str)
                print(f"   Total (convertido): {total}")
                
                # ✅ Validação mínima: campos obrigatórios
                if not cliente or not data:
                    print(f"⚠️ Linha ignorada por dados incompletos:")
                    print(f"   Cliente: '{cliente}', Data: '{data}'")
                    linhas_ignoradas += 1
                    continue
                
                # ✅ Validação do valor total (ACEITA NEGATIVOS)
                try:
                    valor_float = float(total)
                    if valor_float == 0:
                        print(f"⚠️ Linha ignorada: valor zerado")
                        linhas_ignoradas += 1
                        continue
                    
                    # 💸 Marca devoluções
                    if valor_float < 0:
                        devolucoes += 1
                        print(f"💸 DEVOLUÇÃO detectada: R$ {total}")
                        
                except ValueError:
                    print(f"⚠️ Linha ignorada: não foi possível converter total '{total_str}'")
                    linhas_ignoradas += 1
                    continue
                
                # ✅ Cria objeto do faturamento
                item = {
                    "Cod. Cli./For.": cod_cli_for,
                    "Cliente/Fornecedor": cliente,
                    "Data": data,
                    "Total Item": total,  # ✅ PODE SER NEGATIVO
                    "Vendedor": vendedor,
                    "Ref. Produto": ref_produto,
                    "Des. Grupo Completa": grupo,
                    "Marca": marca,
                    "Cidade": cidade,
                    "Estado": estado
                }
                faturamento.append(item)
                
                simbolo = "💸" if valor_float < 0 else "✅"
                print(f"{simbolo} {cliente[:35]}... | R$ {total} | {vendedor[:30]}")
                
            except (IndexError, AttributeError, ValueError) as e:
                print(f"❌ Erro ao processar linha {linhas_processadas}: {e}")
                print(f"   Tipo de erro: {type(e).__name__}")
                linhas_ignoradas += 1
                import traceback
                traceback.print_exc()
                continue

        # 📊 Resumo do processamento
        vendas = len(faturamento) - devolucoes
        print(f"\n{'='*60}")
        print(f"📊 RESUMO DO PROCESSAMENTO")
        print(f"{'='*60}")
        print(f"✅ Registros processados: {len(faturamento)}")
        print(f"   📈 Vendas: {vendas}")
        print(f"   💸 Devoluções: {devolucoes}")
        print(f"⚠️ Linhas ignoradas: {linhas_ignoradas}")
        print(f"📝 Total de linhas analisadas: {linhas_processadas}")
        print(f"{'='*60}\n")
        
        return faturamento

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.post("/processar-pedidos")
async def processar_pedidos(request: Request):
    """
    Processa HTML de email e retorna array de pedidos.
    
    ⚠️ ATENÇÃO: O HTML recebido tem tags <tr> malformadas (não fechadas).
    Usamos html5lib parser que é mais tolerante a HTML malformado.
    
    ESTRUTURA ESPERADA DA TABELA (12 colunas):
    cells[0]  = Data
    cells[1]  = DtEntrPro (Entrega Prod.)
    cells[2]  = Nr. Ped
    cells[3]  = Cod. Cli
    cells[4]  = Cliente
    cells[5]  = Cod. Vend
    cells[6]  = Vendedor
    cells[7]  = Prazo
    cells[8]  = CFOP
    cells[9]  = Sit. Fat
    cells[10] = Total
    cells[11] = Empresa
    """
    try:
        body = await request.body()
        body_str = body.decode('utf-8').strip()
        
        try:
            payload = json.loads(body_str)
            html = payload.get("html_email", "")
        except:
            html = body_str
        
        if not html:
            print("❌ HTML vazio!")
            return []
        
        print(f"📥 HTML recebido: {len(html)} caracteres")
        
        # ✅ USA html5lib PARA PARSEAR HTML MALFORMADO
        try:
            soup = BeautifulSoup(html, 'html5lib')
        except:
            print("⚠️ html5lib não disponível, usando html.parser")
            soup = BeautifulSoup(html, 'html.parser')
        
        pedidos = []
        linhas_processadas = 0
        linhas_ignoradas = 0
        
        print("🔍 Procurando linhas com classe 'destaca' ou 'destacb'...")
        
        for tr in soup.find_all('tr'):
            classes = tr.get('class', []) if tr.get('class') else []
            
            if not any('destac' in str(c) for c in classes):
                continue
            
            cells = tr.find_all('td')
            linhas_processadas += 1
            
            print(f"\n📋 Processando linha {linhas_processadas} com {len(cells)} células")
            
            if len(cells) != 12:
                print(f"⚠️ Linha {linhas_processadas} ignorada: tem {len(cells)} células (esperado 12)")
                linhas_ignoradas += 1
                
                for i in range(min(12, len(cells))):
                    valor = cells[i].get_text(strip=True)[:60]
                    print(f"   cells[{i}] = {valor}")
                
                continue
            
            try:
                data_pedido = cells[0].get_text(strip=True)
                entrega_prod = cells[1].get_text(strip=True)
                nr_pedido = cells[2].get_text(strip=True)
                cod_cli = cells[3].get_text(strip=True)
                cliente = cells[4].get_text(strip=True)
                cod_vend = cells[5].get_text(strip=True)
                vendedor = cells[6].get_text(strip=True)
                prazo = cells[7].get_text(strip=True)
                cfop = cells[8].get_text(strip=True)
                sit_fat = cells[9].get_text(strip=True)
                total_str = cells[10].get_text(strip=True)
                empresa = cells[11].get_text(strip=True)
                
                print(f"   Nr. Pedido: {nr_pedido}")
                print(f"   Cliente: {cliente[:40]}...")
                print(f"   Total (raw): {total_str}")
                
                total = converter_valor_brasileiro(total_str)
                print(f"   Total (convertido): {total}")
                
                if not nr_pedido or not cliente or not data_pedido:
                    print(f"⚠️ Pedido ignorado por dados incompletos:")
                    print(f"   Nr.Ped: '{nr_pedido}', Cliente: '{cliente}', Data: '{data_pedido}'")
                    linhas_ignoradas += 1
                    continue
                
                try:
                    valor_float = float(total)
                    if valor_float <= 0:
                        print(f"⚠️ Pedido {nr_pedido} ignorado: valor inválido R$ {total}")
                        linhas_ignoradas += 1
                        continue
                except ValueError:
                    print(f"⚠️ Pedido {nr_pedido} ignorado: não foi possível converter total '{total_str}'")
                    linhas_ignoradas += 1
                    continue
                
                pedido = {
                    "Data": data_pedido,
                    "Entrega Prod.": entrega_prod if entrega_prod else "",
                    "Nr. Ped": nr_pedido,
                    "Cliente": cliente,
                    "Vendedor": vendedor,
                    "Total": total
                }
                pedidos.append(pedido)
                
                print(f"✅ Pedido {nr_pedido}: {cliente[:40]}... - R$ {total} | {vendedor[:30]}")
                
            except (IndexError, AttributeError, ValueError) as e:
                print(f"❌ Erro ao processar linha {linhas_processadas}: {e}")
                print(f"   Tipo de erro: {type(e).__name__}")
                linhas_ignoradas += 1
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print(f"📊 RESUMO DO PROCESSAMENTO")
        print(f"{'='*60}")
        print(f"✅ Pedidos processados com sucesso: {len(pedidos)}")
        print(f"⚠️ Linhas ignoradas: {linhas_ignoradas}")
        print(f"📝 Total de linhas analisadas: {linhas_processadas}")
        print(f"{'='*60}\n")
        
        return pedidos
    
    except Exception as e:
        print(f"❌ Erro geral no processamento: {e}")
        import traceback
        traceback.print_exc()
        return []
