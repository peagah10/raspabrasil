import os
import time
import random
from datetime import datetime, date
from flask import Flask, render_template_string, request, jsonify, session
from supabase import create_client, Client
import mercadopago

# ========== CONFIGURAÇÕES ==========
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'raspa-brasil-secret-key-2024')

# Configurações do Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# Configurações do Mercado Pago
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN')

# Configurações gerais
TOTAL_RASPADINHAS = 10000

# ========== INICIALIZAÇÃO DOS SERVIÇOS ==========
supabase: Client = None
sdk = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao conectar Supabase: {str(e)}")

if MERCADO_PAGO_ACCESS_TOKEN:
    try:
        sdk = mercadopago.SDK(MERCADO_PAGO_ACCESS_TOKEN)
        print("✅ Mercado Pago conectado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao conectar Mercado Pago: {str(e)}")

# ========== FUNÇÕES DE CONFIGURAÇÃO ==========
def obter_configuracao(chave, valor_padrao):
    """Obter valor de configuração do banco ou retornar padrão"""
    if not supabase:
        return valor_padrao
    
    try:
        response = supabase.table('rb_configuracoes').select('rb_valor').eq(
            'rb_chave', chave
        ).execute()
        
        if response.data:
            return response.data[0]['rb_valor']
        return valor_padrao
    except Exception as e:
        print(f"❌ Erro ao obter configuração {chave}: {str(e)}")
        return valor_padrao

def atualizar_configuracao(chave, valor):
    """Atualizar configuração no banco"""
    if not supabase:
        return False
    
    try:
        # Tentar atualizar primeiro
        response = supabase.table('rb_configuracoes').update({
            'rb_valor': valor
        }).eq('rb_chave', chave).execute()
        
        # Se não atualizou nenhum registro, inserir novo
        if not response.data:
            supabase.table('rb_configuracoes').insert({
                'rb_chave': chave,
                'rb_valor': valor
            }).execute()
        
        return True
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração {chave}: {str(e)}")
        return False

# ========== FUNÇÕES DE ESTATÍSTICAS ==========
def obter_total_vendas():
    """Obter total de vendas aprovadas"""
    if not supabase:
        return 0
    
    try:
        response = supabase.table('rb_vendas').select('rb_quantidade').eq(
            'rb_status', 'completed'
        ).execute()
        
        total = sum(venda['rb_quantidade'] for venda in response.data or [])
        return total
    except Exception as e:
        print(f"❌ Erro ao obter total de vendas: {str(e)}")
        return 0

def obter_total_ganhadores():
    """Obter total de ganhadores (raspadinhas + roda)"""
    if not supabase:
        return 0
    
    try:
        # Ganhadores de raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('rb_id').execute()
        total_raspa = len(response_raspa.data or [])
        
        # Ganhadores da roda
        response_roda = supabase.table('rb_ganhadores_roda').select('rb_id').execute()
        total_roda = len(response_roda.data or [])
        
        return total_raspa + total_roda
    except Exception as e:
        print(f"❌ Erro ao obter total de ganhadores: {str(e)}")
        return 0

def obter_total_afiliados():
    """Obter total de afiliados"""
    if not supabase:
        return 0
    
    try:
        response = supabase.table('rb_afiliados').select('rb_id').execute()
        return len(response.data or [])
    except Exception as e:
        print(f"❌ Erro ao obter total de afiliados: {str(e)}")
        return 0

# ========== FUNÇÕES DE PRÊMIOS (RASPADINHAS) ==========
def obter_premios_disponiveis():
    """Obter quantidade de prêmios disponíveis"""
    premios = {
        'R$ 10,00': int(obter_configuracao('premios_r10', '100')),
        'R$ 20,00': int(obter_configuracao('premios_r20', '50')),
        'R$ 30,00': int(obter_configuracao('premios_r30', '30')),
        'R$ 40,00': int(obter_configuracao('premios_r40', '20')),
        'R$ 50,00': int(obter_configuracao('premios_r50', '15')),
        'R$ 100,00': int(obter_configuracao('premios_r100', '10'))
    }
    return premios

def decrementar_premio(valor):
    """Decrementar quantidade de prêmio"""
    if not supabase:
        return False
    
    mapeamento = {
        'R$ 10,00': 'premios_r10',
        'R$ 20,00': 'premios_r20',
        'R$ 30,00': 'premios_r30',
        'R$ 40,00': 'premios_r40',
        'R$ 50,00': 'premios_r50',
        'R$ 100,00': 'premios_r100'
    }
    
    chave = mapeamento.get(valor)
    if not chave:
        return False
    
    try:
        quantidade_atual = int(obter_configuracao(chave, '0'))
        if quantidade_atual > 0:
            return atualizar_configuracao(chave, str(quantidade_atual - 1))
        return False
    except Exception as e:
        print(f"❌ Erro ao decrementar prêmio {valor}: {str(e)}")
        return False

def sortear_premio():
    """Sorteia um prêmio baseado nas configurações"""
    try:
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            return None, "Sistema temporariamente desativado"

        # Verificar se já vendeu pelo menos 1000 unidades
        total_vendas = obter_total_vendas()
        if total_vendas < 1000:
            print(f"🚫 Prêmios bloqueados: {total_vendas}/1000 vendas")
            return None, "Prêmios serão liberados após 1000 vendas"

        # Chance de ganhar (15% - difícil)
        chance_ganhar = float(obter_configuracao('chance_ganhar', '0.15'))
        if random.random() > chance_ganhar:
            return None, "Não ganhou desta vez"

        # Obter prêmios disponíveis
        premios_disponiveis = obter_premios_disponiveis()
        
        # Lista de prêmios com pesos (mais chances para prêmios menores)
        premios_ponderados = []
        for premio, quantidade in premios_disponiveis.items():
            if quantidade > 0:
                peso = {
                    'R$ 10,00': 40,
                    'R$ 20,00': 25,
                    'R$ 30,00': 20,
                    'R$ 40,00': 15,
                    'R$ 50,00': 10,
                    'R$ 100,00': 3
                }.get(premio, 1)
                
                for _ in range(peso):
                    premios_ponderados.append(premio)
        
        if not premios_ponderados:
            return None, "Todos os prêmios foram distribuídos"
        
        premio_sorteado = random.choice(premios_ponderados)
        
        # Decrementar prêmio
        if decrementar_premio(premio_sorteado):
            return premio_sorteado, f"Parabéns! Você ganhou {premio_sorteado}!"
        else:
            return None, "Erro ao processar prêmio"
        
    except Exception as e:
        print(f"❌ Erro no sorteio: {str(e)}")
        return None, "Erro interno do sistema"

# ========== FUNÇÕES DA RODA BRASIL ==========

def sortear_premio_roda():
    """Sorteia prêmio da Roda Brasil"""
    try:
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao(
            'sistema_ativo', 'true'
        ).lower() == 'true'
        if not sistema_ativo:
            return "VOCÊ PERDEU"

        # Verificar se já vendeu pelo menos 1000 unidades
        total_vendas = obter_total_vendas()
        if total_vendas < 1000:
            print(f"🚫 Prêmios da roda bloqueados: {total_vendas}/1000 vendas")
            return "VOCÊ PERDEU"

        # Chance de ganhar na roda (15% - difícil)
        chance_ganhar = float(obter_configuracao('chance_ganhar_roda', '0.15'))
        if random.random() > chance_ganhar:
            return "VOCÊ PERDEU"

        # Obter prêmios disponíveis da roda
        premios_disponiveis = obter_premios_roda_disponiveis()
        
        # Lista de prêmios com pesos
        premios_ponderados = []
        for premio, quantidade in premios_disponiveis.items():
            if quantidade > 0:
                peso = {
                    'R$ 1,00': 25,
                    'R$ 5,00': 20, 
                    'R$ 10,00': 15,
                    'R$ 100,00': 10,
                    'R$ 300,00': 5,
                    'R$ 500,00': 3,
                    'R$ 1000,00': 2
                }.get(premio, 1)
                
                for _ in range(peso):
                    premios_ponderados.append(premio)
        
        if not premios_ponderados:
            return "VOCÊ PERDEU"
        
        premio_sorteado = random.choice(premios_ponderados)
        
        # Decrementar prêmio
        decrementar_premio_roda(premio_sorteado)
        
        return premio_sorteado
        
    except Exception as e:
        print(f"❌ Erro no sorteio da roda: {str(e)}")
        return "VOCÊ PERDEU"

def obter_premios_roda_disponiveis():
    """Obter quantidade de prêmios disponíveis da Roda Brasil"""
    premios = {
        'R$ 1,00': int(obter_configuracao('premios_roda_r1', '50')),
        'R$ 5,00': int(obter_configuracao('premios_roda_r5', '30')),
        'R$ 10,00': int(obter_configuracao('premios_roda_r10', '20')),
        'R$ 100,00': int(obter_configuracao('premios_roda_r100', '10')),
        'R$ 300,00': int(obter_configuracao('premios_roda_r300', '5')),
        'R$ 500,00': int(obter_configuracao('premios_roda_r500', '3')),
        'R$ 1000,00': int(obter_configuracao('premios_roda_r1000', '2'))
    }
    return premios

def decrementar_premio_roda(valor):
    """Decrementar quantidade de prêmio da roda"""
    if not supabase:
        return False
    
    mapeamento = {
        'R$ 1,00': 'premios_roda_r1',
        'R$ 5,00': 'premios_roda_r5', 
        'R$ 10,00': 'premios_roda_r10',
        'R$ 100,00': 'premios_roda_r100',
        'R$ 300,00': 'premios_roda_r300',
        'R$ 500,00': 'premios_roda_r500',
        'R$ 1000,00': 'premios_roda_r1000'
    }
    
    chave = mapeamento.get(valor)
    if not chave:
        return False
    
    try:
        quantidade_atual = int(obter_configuracao(chave, '0'))
        if quantidade_atual > 0:
            return atualizar_configuracao(chave, str(quantidade_atual - 1))
        return False
    except Exception as e:
        print(f"❌ Erro ao decrementar prêmio da roda {valor}: {str(e)}")
        return False

# ========== FUNÇÕES DE AFILIADOS ==========
def gerar_codigo_afiliado():
    """Gerar código único para afiliado"""
    import string
    
    while True:
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Verificar se já existe no banco
        if supabase:
            try:
                response = supabase.table('rb_afiliados').select('rb_codigo').eq(
                    'rb_codigo', codigo
                ).execute()
                
                if not response.data:
                    return codigo
            except:
                pass
        else:
            return codigo

def processar_comissao_afiliado(afiliado_id, valor_venda):
    """Processar comissão do afiliado"""
    if not supabase or not afiliado_id:
        return False
    
    try:
        percentual = float(obter_configuracao('percentual_comissao_afiliado', '50'))
        comissao = (valor_venda * percentual) / 100
        
        # Atualizar totais do afiliado
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_id', afiliado_id
        ).execute()
        
        if response.data:
            afiliado = response.data[0]
            novo_total_vendas = (afiliado['rb_total_vendas'] or 0) + 1
            nova_comissao_total = (afiliado['rb_total_comissao'] or 0) + comissao
            novo_saldo = (afiliado['rb_saldo_disponivel'] or 0) + comissao
            
            supabase.table('rb_afiliados').update({
                'rb_total_vendas': novo_total_vendas,
                'rb_total_comissao': nova_comissao_total,
                'rb_saldo_disponivel': novo_saldo
            }).eq('rb_id', afiliado_id).execute()
            
            return True
            
    except Exception as e:
        print(f"❌ Erro ao processar comissão: {str(e)}")
        return False

# ========== ROTAS PRINCIPAIS ==========
@app.route('/')
def index():
    """Página inicial"""
    # Processar clique de afiliado se houver
    ref_code = request.args.get('ref')
    if ref_code and supabase:
        try:
            # Buscar afiliado
            afiliado_response = supabase.table('rb_afiliados').select('rb_id').eq(
                'rb_codigo', ref_code
            ).eq('rb_status', 'ativo').execute()
            
            if afiliado_response.data:
                afiliado_id = afiliado_response.data[0]['rb_id']
                
                # Registrar clique
                supabase.table('rb_afiliado_clicks').insert({
                    'rb_afiliado_id': afiliado_id,
                    'rb_ip_visitor': request.remote_addr,
                    'rb_user_agent': request.headers.get('User-Agent', '')[:500],
                    'rb_referrer': request.headers.get('Referer', '')
                }).execute()
                
                # Incrementar contador de cliques
                supabase.table('rb_afiliados').update({
                    'rb_total_clicks': supabase.table('rb_afiliados').select('rb_total_clicks').eq('rb_id', afiliado_id).execute().data[0]['rb_total_clicks'] + 1
                }).eq('rb_id', afiliado_id).execute()
                
        except Exception as e:
            print(f"❌ Erro ao processar clique de afiliado: {str(e)}")
    
    # Renderizar HTML (usar o HTML fornecido anteriormente)
    with open('index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    return render_template_string(html_content)

# ========== ROTAS DE PAGAMENTO (RASPADINHAS) ==========
@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Criar pagamento via Mercado Pago"""
    try:
        data = request.json
        quantidade = int(data.get('quantidade', 1))
        ref_code = data.get('ref_code')
        
        if quantidade < 1 or quantidade > 10:
            return jsonify({'error': 'Quantidade inválida'}), 400
        
        valor_total = quantidade * 1.00
        
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        if not sistema_ativo:
            return jsonify({'error': 'Sistema temporariamente desativado'}), 400
        
        if not sdk:
            return jsonify({'error': 'Sistema de pagamento indisponível'}), 500
        
        # Buscar afiliado se houver código
        afiliado_id = None
        if ref_code and supabase:
            try:
                afiliado_response = supabase.table('rb_afiliados').select('rb_id').eq(
                    'rb_codigo', ref_code
                ).eq('rb_status', 'ativo').execute()
                
                if afiliado_response.data:
                    afiliado_id = afiliado_response.data[0]['rb_id']
            except Exception as e:
                print(f"❌ Erro ao buscar afiliado: {str(e)}")
        
        # Criar pagamento no Mercado Pago
        payment_data = {
            "transaction_amount": valor_total,
            "description": f"Raspa Brasil - {quantidade} raspadinha(s)",
            "payment_method_id": "pix",
            "payer": {"email": "cliente@email.com"},
            "external_reference": f"raspa_{int(time.time())}_{quantidade}"
        }
        
        payment = sdk.payment().create(payment_data)
        payment_info = payment.get("response", {})
        
        if payment_info and payment_info.get("id"):
            payment_id = payment_info["id"]
            
            # Salvar no banco
            if supabase:
                try:
                    supabase.table('rb_vendas').insert({
                        'rb_quantidade': quantidade,
                        'rb_valor_total': valor_total,
                        'rb_payment_id': str(payment_id),
                        'rb_status': 'pending',
                        'rb_tipo': 'raspadinha',
                        'rb_afiliado_id': afiliado_id,
                        'rb_ip_cliente': request.remote_addr,
                        'rb_user_agent': request.headers.get('User-Agent', '')[:500],
                    }).execute()
                except Exception as e:
                    print(f"❌ Erro ao salvar venda: {str(e)}")
            
            return jsonify({
                'id': payment_id,
                'qr_code': payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code"),
                'qr_code_base64': payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code_base64"),
                'amount': valor_total
            })
        else:
            return jsonify({'error': 'Erro ao criar pagamento'}), 500
            
    except Exception as e:
        print(f"❌ Erro ao criar pagamento: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verificar status do pagamento"""
    try:
        if not sdk:
            return jsonify({'status': 'error', 'message': 'Sistema de pagamento indisponível'})
        
        payment = sdk.payment().get(payment_id)
        payment_info = payment.get("response", {})
        
        if payment_info:
            status = payment_info.get("status")
            
            # Atualizar no banco se aprovado
            if status == "approved" and supabase:
                try:
                    # Atualizar status da venda
                    venda_response = supabase.table('rb_vendas').update({
                        'rb_status': 'completed'
                    }).eq('rb_payment_id', payment_id).execute()
                    
                    # Processar comissão se for venda via afiliado
                    if venda_response.data:
                        venda = venda_response.data[0]
                        if venda.get('rb_afiliado_id'):
                            processar_comissao_afiliado(
                                venda['rb_afiliado_id'], 
                                venda['rb_valor_total']
                            )
                            
                except Exception as e:
                    print(f"❌ Erro ao atualizar status: {str(e)}")
            
            return jsonify({'status': status})
        else:
            return jsonify({'status': 'error'})
            
    except Exception as e:
        print(f"❌ Erro ao verificar pagamento: {str(e)}")
        return jsonify({'status': 'error'})

@app.route('/raspar', methods=['POST'])
def raspar():
    """Processar raspagem de uma bandeira"""
    try:
        premio, mensagem = sortear_premio()
        
        if premio:
            codigo = f"RB-{random.randint(10000, 99999)}-{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"
            
            return jsonify({
                'ganhou': True,
                'valor': premio,
                'codigo': codigo,
                'mensagem': mensagem
            })
        else:
            return jsonify({
                'ganhou': False,
                'mensagem': mensagem or "Não foi desta vez!"
            })
            
    except Exception as e:
        print(f"❌ Erro ao processar raspagem: {str(e)}")
        return jsonify({'erro': 'Erro interno do servidor'}), 500

@app.route('/salvar_ganhador', methods=['POST'])
def salvar_ganhador():
    """Salvar dados do ganhador"""
    try:
        data = request.json
        nome = data.get('nome', '').strip()
        valor = data.get('valor', '').strip()
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')
        codigo = data.get('codigo', '').strip()
        
        if not all([nome, valor, chave_pix, codigo]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if len(chave_pix) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema de banco indisponível'})
        
        # Salvar ganhador
        ganhador_data = {
            'rb_codigo': codigo,
            'rb_nome': nome,
            'rb_valor': valor,
            'rb_chave_pix': chave_pix,
            'rb_tipo_chave': tipo_chave,
            'rb_status_pagamento': 'pendente'
        }
        
        ganhador_response = supabase.table('rb_ganhadores').insert(ganhador_data).execute()
        
        if ganhador_response.data:
            ganhador_id = ganhador_response.data[0]['rb_id']
            
            # Criar solicitação de saque automaticamente
            valor_numerico = float(valor.replace('R$ ', '').replace(',', '.'))
            saque_data = {
                'rb_ganhador_id': ganhador_id,
                'rb_valor': valor_numerico,
                'rb_chave_pix': chave_pix,
                'rb_tipo_chave': tipo_chave,
                'rb_status': 'solicitado'
            }
            
            supabase.table('rb_saques_ganhadores').insert(saque_data).execute()
            
            return jsonify({'sucesso': True, 'codigo': codigo})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar no banco'})
            
    except Exception as e:
        print(f"❌ Erro ao salvar ganhador: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS DA RODA BRASIL ==========

@app.route('/create_payment_roda', methods=['POST'])
def create_payment_roda():
    """Criar pagamento para Roda Brasil"""
    try:
        data = request.json
        quantidade = int(data.get('quantidade', 1))
        
        if quantidade < 1 or quantidade > 10:
            return jsonify({'error': 'Quantidade inválida'}), 400
        
        valor_total = quantidade * 1.00
        
        # Verificar se o sistema está ativo
        sistema_ativo = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        if not sistema_ativo:
            return jsonify({'error': 'Sistema temporariamente desativado'}), 400
        
        if not sdk:
            return jsonify({'error': 'Sistema de pagamento indisponível'}), 500
        
        # Criar pagamento no Mercado Pago
        payment_data = {
            "transaction_amount": valor_total,
            "description": f"Roda Brasil - {quantidade} ficha(s)",
            "payment_method_id": "pix",
            "payer": {"email": "cliente@email.com"},
            "external_reference": f"roda_{int(time.time())}_{quantidade}"
        }
        
        payment = sdk.payment().create(payment_data)
        payment_info = payment.get("response", {})
        
        if payment_info and payment_info.get("id"):
            payment_id = payment_info["id"]
            
            # Salvar no banco
            if supabase:
                try:
                    supabase.table('rb_vendas').insert({
                        'rb_quantidade': quantidade,
                        'rb_valor_total': valor_total,
                        'rb_payment_id': str(payment_id),
                        'rb_status': 'pending',
                        'rb_tipo': 'roda_brasil',
                        'rb_ip_cliente': request.remote_addr,
                        'rb_user_agent': request.headers.get('User-Agent', '')[:500],
                    }).execute()
                except Exception as e:
                    print(f"❌ Erro ao salvar venda da roda: {str(e)}")
            
            return jsonify({
                'id': payment_id,
                'qr_code': payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code"),
                'qr_code_base64': payment_info.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code_base64"),
                'amount': valor_total
            })
        else:
            return jsonify({'error': 'Erro ao criar pagamento'}), 500
            
    except Exception as e:
        print(f"❌ Erro ao criar pagamento da roda: {str(e)}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/check_payment_roda/<payment_id>')
def check_payment_roda(payment_id):
    """Verificar status do pagamento da Roda Brasil"""
    try:
        if not sdk:
            return jsonify({'status': 'error', 'message': 'Sistema de pagamento indisponível'})
        
        payment = sdk.payment().get(payment_id)
        payment_info = payment.get("response", {})
        
        if payment_info:
            status = payment_info.get("status")
            
            # Atualizar no banco se aprovado
            if status == "approved" and supabase:
                try:
                    supabase.table('rb_vendas').update({
                        'rb_status': 'completed'
                    }).eq('rb_payment_id', payment_id).execute()
                except Exception as e:
                    print(f"❌ Erro ao atualizar status da roda: {str(e)}")
            
            return jsonify({'status': status})
        else:
            return jsonify({'status': 'error'})
            
    except Exception as e:
        print(f"❌ Erro ao verificar pagamento da roda: {str(e)}")
        return jsonify({'status': 'error'})

@app.route('/girar_roda', methods=['POST'])
def girar_roda():
    """Endpoint para girar a roleta"""
    try:
        resultado = sortear_premio_roda()
        return jsonify({'resultado': resultado})
    except Exception as e:
        print(f"❌ Erro ao girar roda: {str(e)}")
        return jsonify({'resultado': 'VOCÊ PERDEU'})

@app.route('/salvar_ganhador_roda', methods=['POST'])
def salvar_ganhador_roda():
    """Salvar ganhador da Roda Brasil"""
    try:
        data = request.json
        nome = data.get('nome', '').strip()
        cpf = data.get('cpf', '').strip()
        valor = data.get('valor', '').strip()
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')
        codigo = data.get('codigo', '').strip()
        
        if not all([nome, cpf, valor, chave_pix, codigo]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF deve ter 11 dígitos'})
        
        if len(chave_pix) < 5:
            return jsonify({'sucesso': False, 'erro': 'Chave PIX inválida'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema de banco indisponível'})
        
        # Salvar ganhador da roda
        ganhador_data = {
            'rb_codigo': codigo,
            'rb_nome': nome,
            'rb_cpf': cpf,
            'rb_valor': valor,
            'rb_chave_pix': chave_pix,
            'rb_tipo_chave': tipo_chave,
            'rb_status_pagamento': 'pendente'
        }
        
        ganhador_response = supabase.table('rb_ganhadores_roda').insert(ganhador_data).execute()
        
        if ganhador_response.data:
            ganhador_id = ganhador_response.data[0]['rb_id']
            
            # Criar solicitação de saque automaticamente
            valor_numerico = float(valor.replace('R$ ', '').replace(',', '.'))
            saque_data = {
                'rb_ganhador_id': ganhador_id,
                'rb_valor': valor_numerico,
                'rb_chave_pix': chave_pix,
                'rb_tipo_chave': tipo_chave,
                'rb_status': 'solicitado'
            }
            
            supabase.table('rb_saques_ganhadores').insert(saque_data).execute()
            
            return jsonify({'sucesso': True, 'codigo': codigo})
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao salvar no banco'})
            
    except Exception as e:
        print(f"❌ Erro ao salvar ganhador da roda: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS DE AFILIADOS ==========
@app.route('/cadastrar_afiliado', methods=['POST'])
def cadastrar_afiliado():
    """Cadastrar novo afiliado"""
    try:
        data = request.json
        nome = data.get('nome', '').strip()
        telefone = data.get('telefone', '').strip()
        email = data.get('email', '').strip()
        cpf = data.get('cpf', '').strip()
        
        if not all([nome, telefone, email, cpf]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if '@' not in email:
            return jsonify({'sucesso': False, 'erro': 'E-mail inválido'})
        
        if len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF deve ter 11 dígitos'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema de banco indisponível'})
        
        # Verificar se CPF já existe
        cpf_response = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_cpf', cpf
        ).execute()
        
        if cpf_response.data:
            return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
        
        # Verificar se e-mail já existe
        email_response = supabase.table('rb_afiliados').select('rb_id').eq(
            'rb_email', email
        ).execute()
        
        if email_response.data:
            return jsonify({'sucesso': False, 'erro': 'E-mail já cadastrado'})
        
        # Criar afiliado
        codigo = gerar_codigo_afiliado()
        afiliado_data = {
            'rb_codigo': codigo,
            'rb_nome': nome,
            'rb_email': email,
            'rb_telefone': telefone,
            'rb_cpf': cpf,
            'rb_status': 'ativo'
        }
        
        response = supabase.table('rb_afiliados').insert(afiliado_data).execute()
        
        if response.data:
            afiliado = response.data[0]
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'codigo': afiliado['rb_codigo'],
                    'nome': afiliado['rb_nome'],
                    'email': afiliado['rb_email'],
                    'total_clicks': 0,
                    'total_vendas': 0,
                    'total_comissao': 0,
                    'saldo_disponivel': 0
                }
            })
        else:
            return jsonify({'sucesso': False, 'erro': 'Erro ao criar afiliado'})
            
    except Exception as e:
        print(f"❌ Erro ao cadastrar afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/login_afiliado', methods=['POST'])
def login_afiliado():
    """Login do afiliado por CPF"""
    try:
        data = request.json
        cpf = data.get('cpf', '').strip()
        
        if not cpf or len(cpf) != 11:
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_cpf', cpf
        ).eq('rb_status', 'ativo').execute()
        
        if response.data:
            afiliado = response.data[0]
            return jsonify({
                'sucesso': True,
                'afiliado': {
                    'codigo': afiliado['rb_codigo'],
                    'nome': afiliado['rb_nome'],
                    'email': afiliado['rb_email'],
                    'chave_pix': afiliado.get('rb_chave_pix'),
                    'tipo_chave_pix': afiliado.get('rb_tipo_chave_pix'),
                    'total_clicks': afiliado['rb_total_clicks'] or 0,
                    'total_vendas': afiliado['rb_total_vendas'] or 0,
                    'total_comissao': float(afiliado['rb_total_comissao'] or 0),
                    'saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0)
                }
            })
        else:
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro no login afiliado: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/atualizar_pix_afiliado', methods=['POST'])
def atualizar_pix_afiliado():
    """Atualizar chave PIX do afiliado"""
    try:
        data = request.json
        codigo = data.get('codigo', '').strip()
        chave_pix = data.get('chave_pix', '').strip()
        tipo_chave = data.get('tipo_chave', 'cpf')
        
        if not all([codigo, chave_pix]):
            return jsonify({'sucesso': False, 'erro': 'Dados incompletos'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
        response = supabase.table('rb_afiliados').update({
            'rb_chave_pix': chave_pix,
            'rb_tipo_chave_pix': tipo_chave
        }).eq('rb_codigo', codigo).execute()
        
        if response.data:
            return jsonify({'sucesso': True})
        else:
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
            
    except Exception as e:
        print(f"❌ Erro ao atualizar PIX: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/solicitar_saque_afiliado', methods=['POST'])
def solicitar_saque_afiliado():
    """Solicitar saque de comissão"""
    try:
        data = request.json
        codigo = data.get('codigo', '').strip()
        
        if not codigo:
            return jsonify({'sucesso': False, 'erro': 'Código não fornecido'})
        
        if not supabase:
            return jsonify({'sucesso': False, 'erro': 'Sistema indisponível'})
        
        # Buscar afiliado
        response = supabase.table('rb_afiliados').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if not response.data:
            return jsonify({'sucesso': False, 'erro': 'Afiliado não encontrado'})
        
        afiliado = response.data[0]
        saldo = float(afiliado['rb_saldo_disponivel'] or 0)
        saque_minimo = float(obter_configuracao('saque_minimo_afiliado', '10'))
        
        if saldo < saque_minimo:
            return jsonify({'sucesso': False, 'erro': f'Saldo mínimo para saque: R$ {saque_minimo:.2f}'})
        
        if not afiliado.get('rb_chave_pix'):
            return jsonify({'sucesso': False, 'erro': 'Configure sua chave PIX primeiro'})
        
        # Criar solicitação de saque
        saque_data = {
            'rb_afiliado_id': afiliado['rb_id'],
            'rb_valor': saldo,
            'rb_chave_pix': afiliado['rb_chave_pix'],
            'rb_tipo_chave': afiliado.get('rb_tipo_chave_pix', 'cpf'),
            'rb_status': 'solicitado'
        }
        
        supabase.table('rb_saques_afiliados').insert(saque_data).execute()
        
        # Zerar saldo do afiliado
        supabase.table('rb_afiliados').update({
            'rb_saldo_disponivel': 0
        }).eq('rb_id', afiliado['rb_id']).execute()
        
        return jsonify({'sucesso': True, 'valor': saldo})
        
    except Exception as e:
        print(f"❌ Erro ao solicitar saque: {str(e)}")
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

# ========== ROTAS ADMINISTRATIVAS ==========
@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login administrativo"""
    try:
        data = request.json
        senha = data.get('senha', '').strip()
        
        if not senha:
            return jsonify({'success': False, 'message': 'Senha não fornecida'})
        
        # Por enquanto, usar senha simples até implementar tabela admin
        if senha == 'paulo10@admin':
            session['admin_logado'] = True
            return jsonify({'success': True, 'message': 'Login realizado com sucesso'})
        
        # Verificar no banco se existir
        if supabase:
            try:
                response = supabase.table('rb_admins').select('*').eq(
                    'rb_senha', senha
                ).eq('rb_ativo', True).execute()
                if response.data:
                    admin = response.data[0]
                    session['admin_logado'] = True
                    session['admin_usuario'] = admin['rb_usuario']
                    
                    # Atualizar último login
                    supabase.table('rb_admins').update({
                        'rb_ultimo_login': datetime.now().isoformat()
                    }).eq('rb_id', admin['rb_id']).execute()
                    
                    return jsonify({'success': True, 'message': f'Bem-vindo, {admin["rb_nome"]}'})
            except Exception as e:
                print(f"❌ Erro ao verificar admin no banco: {str(e)}")
        
        return jsonify({'success': False, 'message': 'Senha incorreta'})
        
    except Exception as e:
        print(f"❌ Erro no login admin: {str(e)}")
        return jsonify({'success': False, 'message': 'Erro interno'})

@app.route('/admin/toggle_sistema', methods=['POST'])
def toggle_sistema():
    """Alterna status do sistema"""
    if not session.get('admin_logado'):
        return jsonify({'success': False, 'mensagem': 'Acesso negado'})
    
    try:
        sistema_atual = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        novo_status = 'false' if sistema_atual else 'true'
        
        if atualizar_configuracao('sistema_ativo', novo_status):
            status_texto = 'ativado' if novo_status == 'true' else 'desativado'
            return jsonify({'success': True, 'mensagem': f'Sistema {status_texto} com sucesso'})
        else:
            return jsonify({'success': False, 'mensagem': 'Erro ao atualizar sistema'})
    except Exception as e:
        print(f"❌ Erro ao alternar sistema: {str(e)}")
        return jsonify({'success': False, 'mensagem': str(e)})

@app.route('/validar_codigo', methods=['POST'])
def validar_codigo():
    """Valida código de ganhador"""
    data = request.json
    codigo = data.get('codigo', '').strip().upper()
    
    if not codigo:
        return jsonify({'valido': False, 'mensagem': 'Código não fornecido'})
    
    if not supabase:
        return jsonify({'valido': False, 'mensagem': 'Sistema de validação indisponível'})
    
    try:
        # Verificar nas raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if response_raspa.data:
            ganhador = response_raspa.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - RASPADINHA - {ganhador["rb_nome"]} - {ganhador["rb_valor"]} - Status: {ganhador.get("rb_status_pagamento", "pendente")}'
            })
        
        # Verificar na Roda Brasil
        response_roda = supabase.table('rb_ganhadores_roda').select('*').eq(
            'rb_codigo', codigo
        ).execute()
        
        if response_roda.data:
            ganhador = response_roda.data[0]
            return jsonify({
                'valido': True,
                'mensagem': f'✅ Código válido - RODA BRASIL - {ganhador["rb_nome"]} - {ganhador["rb_valor"]} - Status: {ganhador.get("rb_status_pagamento", "pendente")}'
            })
        
        return jsonify({'valido': False, 'mensagem': '❌ Código não encontrado ou inválido'})
            
    except Exception as e:
        print(f"❌ Erro ao validar código: {str(e)}")
        return jsonify({'valido': False, 'mensagem': 'Erro ao validar código'})

@app.route('/admin/premiados')
def admin_premiados():
    """Lista de premiados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'premiados': []})
    
    try:
        # Buscar ganhadores de raspadinhas
        response_raspa = supabase.table('rb_ganhadores').select('*').order(
            'rb_data_criacao', desc=True
        ).limit(25).execute()
        
        # Buscar ganhadores da roda
        response_roda = supabase.table('rb_ganhadores_roda').select('*').order(
            'rb_data_criacao', desc=True
        ).limit(25).execute()
        
        premiados = []
        
        # Adicionar ganhadores de raspadinhas
        for ganhador in (response_raspa.data or []):
            ganhador['rb_tipo'] = 'RASPADINHA'
            premiados.append(ganhador)
        
        # Adicionar ganhadores da roda
        for ganhador in (response_roda.data or []):
            ganhador['rb_tipo'] = 'RODA BRASIL'
            premiados.append(ganhador)
        
        # Ordenar por data de criação
        premiados.sort(key=lambda x: x['rb_data_criacao'], reverse=True)
        
        return jsonify({'premiados': premiados[:50]})  # Limitar a 50 resultados
        
    except Exception as e:
        print(f"❌ Erro ao listar premiados: {str(e)}")
        return jsonify({'premiados': []})

@app.route('/admin/afiliados')
def admin_afiliados():
    """Lista de afiliados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'afiliados': []})
    
    try:
        response = supabase.table('rb_afiliados').select('*').order(
            'rb_data_criacao', desc=True
        ).execute()
        
        afiliados = []
        for afiliado in response.data or []:
            afiliados.append({
                'id': afiliado['rb_id'],
                'codigo': afiliado['rb_codigo'],
                'nome': afiliado['rb_nome'],
                'email': afiliado['rb_email'],
                'telefone': afiliado['rb_telefone'],
                'total_clicks': afiliado['rb_total_clicks'] or 0,
                'total_vendas': afiliado['rb_total_vendas'] or 0,
                'total_comissao': float(afiliado['rb_total_comissao'] or 0),
                'saldo_disponivel': float(afiliado['rb_saldo_disponivel'] or 0),
                'status': afiliado['rb_status'],
                'data_criacao': afiliado['rb_data_criacao']
            })
        
        return jsonify({'afiliados': afiliados})
    except Exception as e:
        print(f"❌ Erro ao listar afiliados: {str(e)}")
        return jsonify({'afiliados': []})

@app.route('/admin/saques_ganhadores')
def admin_saques_ganhadores():
    """Lista de saques de ganhadores para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'saques': []})
    
    try:
        # Buscar saques
        saques_response = supabase.table('rb_saques_ganhadores').select('*').order(
            'rb_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do ganhador de raspadinha
            ganhador_raspa = None
            try:
                ganhador_response = supabase.table('rb_ganhadores').select('rb_nome, rb_codigo').eq(
                    'rb_id', saque['rb_ganhador_id']
                ).execute()
                if ganhador_response.data:
                    ganhador_raspa = ganhador_response.data[0]
            except:
                pass
            
            # Buscar dados do ganhador da roda
            ganhador_roda = None
            try:
                ganhador_roda_response = supabase.table('rb_ganhadores_roda').select('rb_nome, rb_codigo').eq(
                    'rb_id', saque['rb_ganhador_id']
                ).execute()
                if ganhador_roda_response.data:
                    ganhador_roda = ganhador_roda_response.data[0]
            except:
                pass
            
            saque_completo = saque.copy()
            if ganhador_raspa:
                saque_completo['rb_ganhadores'] = ganhador_raspa
                saque_completo['rb_tipo'] = 'RASPADINHA'
            elif ganhador_roda:
                saque_completo['rb_ganhadores'] = ganhador_roda
                saque_completo['rb_tipo'] = 'RODA BRASIL'
            else:
                saque_completo['rb_ganhadores'] = {'rb_nome': 'Nome não encontrado', 'rb_codigo': 'N/A'}
                saque_completo['rb_tipo'] = 'DESCONHECIDO'
            
            saques.append(saque_completo)
        
        return jsonify({'saques': saques})
    except Exception as e:
        print(f"❌ Erro ao listar saques de ganhadores: {str(e)}")
        return jsonify({'saques': []})

@app.route('/admin/saques_afiliados')
def admin_saques_afiliados():
    """Lista de saques de afiliados para admin"""
    if not session.get('admin_logado'):
        return jsonify({'error': 'Acesso negado'})
    
    if not supabase:
        return jsonify({'saques': []})
    
    try:
        # Buscar saques
        saques_response = supabase.table('rb_saques_afiliados').select('*').order(
            'rb_data_solicitacao', desc=True
        ).execute()
        
        saques = []
        for saque in (saques_response.data or []):
            # Buscar dados do afiliado separadamente
            afiliado_response = supabase.table('rb_afiliados').select('rb_nome, rb_codigo, rb_total_vendas').eq(
                'rb_id', saque['rb_afiliado_id']
            ).execute()
            
            saque_completo = saque.copy()
            if afiliado_response.data:
                saque_completo['rb_afiliados'] = afiliado_response.data[0]
            else:
                saque_completo['rb_afiliados'] = {'rb_nome': 'Nome não encontrado', 'rb_codigo': 'N/A', 'rb_total_vendas': 0}
            
            saques.append(saque_completo)
        
        return jsonify({'saques': saques})
    except Exception as e:
        print(f"❌ Erro ao listar saques de afiliados: {str(e)}")
        return jsonify({'saques': []})

@app.route('/admin/stats')
def admin_stats():
    """Estatísticas do sistema incluindo afiliados"""
    try:
        vendidas = obter_total_vendas()
        ganhadores = obter_total_ganhadores()
        afiliados = obter_total_afiliados()
        
        # Estatísticas do dia
        vendas_hoje = 0
        vendas_afiliados_hoje = 0
        if supabase:
            try:
                hoje = date.today().isoformat()
                vendas_response = supabase.table('rb_vendas').select('*').gte(
                    'rb_data_criacao', hoje + ' 00:00:00'
                ).eq('rb_status', 'completed').execute()
                
                vendas_hoje = len(vendas_response.data or [])
                vendas_afiliados_hoje = len([v for v in (vendas_response.data or []) if v.get('rb_afiliado_id')])
                
            except Exception as e:
                print(f"❌ Erro ao obter vendas do dia: {str(e)}")

        # Calcular prêmios restantes (raspadinhas + roda)
        premios_raspa = obter_premios_disponiveis()
        premios_roda = obter_premios_roda_disponiveis()
        total_premios_restantes = sum(premios_raspa.values()) + sum(premios_roda.values())

        return jsonify({
            'vendidas': vendidas,
            'ganhadores': ganhadores,
            'afiliados': afiliados,
            'vendas_hoje': vendas_hoje,
            'vendas_afiliados_hoje': vendas_afiliados_hoje,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS - vendidas,
            'premios_restantes': total_premios_restantes,
            'supabase_conectado': supabase is not None,
            'mercadopago_conectado': sdk is not None,
            'sistema_ativo': obter_configuracao(
                'sistema_ativo', 'true'
            ).lower() == 'true'
        })

    except Exception as e:
        print(f"❌ Erro ao obter estatísticas: {str(e)}")
        return jsonify({
            'vendidas': 0,
            'ganhadores': 0,
            'afiliados': 0,
            'vendas_hoje': 0,
            'vendas_afiliados_hoje': 0,
            'total_raspadinhas': TOTAL_RASPADINHAS,
            'restantes': TOTAL_RASPADINHAS,
            'premios_restantes': 0,
            'supabase_conectado': False,
            'mercadopago_conectado': False,
            'sistema_ativo': True
        })

# ========== ROTAS DE SAQUE ==========
@app.route('/admin/pagar_saque_ganhador/<int:saque_id>', methods=['POST'])
def pagar_saque_ganhador(saque_id):
    """Marca saque de ganhador como pago"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        response = supabase.table('rb_saques_ganhadores').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            return jsonify({"sucesso": True, "mensagem": "Saque marcado como pago"})
        else:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500

@app.route('/admin/excluir_saque_ganhador/<int:saque_id>', methods=['DELETE'])
def excluir_saque_ganhador(saque_id):
    """Exclui saque de ganhador (só se estiver pago)"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        # Verificar se está pago
        check_response = supabase.table('rb_saques_ganhadores').select('rb_status').eq(
            'rb_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['rb_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('rb_saques_ganhadores').delete().eq(
            'rb_id', saque_id
        ).execute()
        
        return jsonify({"sucesso": True, "mensagem": "Saque excluído com sucesso"})
        
    except Exception as e:
        print(f"❌ Erro ao excluir saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500

@app.route('/admin/pagar_saque_afiliado/<int:saque_id>', methods=['POST'])
def pagar_saque_afiliado(saque_id):
    """Marca saque de afiliado como pago"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        response = supabase.table('rb_saques_afiliados').update({
            'rb_status': 'pago',
            'rb_data_pagamento': datetime.now().isoformat()
        }).eq('rb_id', saque_id).execute()
        
        if response.data:
            return jsonify({"sucesso": True, "mensagem": "Saque marcado como pago"})
        else:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
    except Exception as e:
        print(f"❌ Erro ao pagar saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500

@app.route('/admin/excluir_saque_afiliado/<int:saque_id>', methods=['DELETE'])
def excluir_saque_afiliado(saque_id):
    """Exclui saque de afiliado (só se estiver pago)"""
    if not session.get('admin_logado'):
        return jsonify({"sucesso": False, "erro": "Acesso negado"}), 403
    
    if not supabase:
        return jsonify({"sucesso": False, "erro": "Sistema indisponível"}), 500
    
    try:
        # Verificar se está pago
        check_response = supabase.table('rb_saques_afiliados').select('rb_status').eq(
            'rb_id', saque_id
        ).execute()
        
        if not check_response.data:
            return jsonify({"sucesso": False, "erro": "Saque não encontrado"}), 404
            
        if check_response.data[0]['rb_status'] != 'pago':
            return jsonify({"sucesso": False, "erro": "Só é possível excluir saques pagos"}), 400
        
        # Excluir
        response = supabase.table('rb_saques_afiliados').delete().eq(
            'rb_id', saque_id
        ).execute()
        
        return jsonify({"sucesso": True, "mensagem": "Saque excluído com sucesso"})
        
    except Exception as e:
        print(f"❌ Erro ao excluir saque: {str(e)}")
        return jsonify({"sucesso": False, "erro": "Erro interno do servidor"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando Raspa Brasil + Roda Brasil...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅' if sdk else '❌'}")
    print(f"🔗 Supabase: {'✅' if supabase else '❌'}")
    print(f"👥 Sistema de Afiliados: ✅")
    print(f"🎰 Roda Brasil: ✅")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
