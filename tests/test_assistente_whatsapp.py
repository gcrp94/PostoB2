"""B2 Assistente no WhatsApp: quem pode falar, o que responde, como formata. Sem internet e sem a biblioteca de sessão.

    python -m pytest tests/test_assistente_whatsapp.py

O robô é uma conexão NÃO oficial num chip dedicado: o que importa provar aqui é que ele NÃO responde a quem não foi
autorizado, nem em grupo, nem a si mesmo, e que não vira uma máquina de mandar mensagem (limite por pessoa).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src import assistente_whatsapp as wa
from src.assistente import Resposta

EU = "5542999990001"


def roteador(autorizados=(EU,), responder=None, relogio=None):
    certo = responder or (lambda c: Resposta("📊 Resumo", f"você pediu: {c}", (("📦 Estoque", "estoque centro"), ("🚨 Alertas", "alertas"))))
    return wa.Roteador(certo, lambda: list(autorizados), relogio or (lambda: 0.0))


# ------------------------------------------------------------------ números ---
@pytest.mark.parametrize("entrada,esperado", [
    ("(42) 99999-0001", "5542999990001"), ("+55 42 99999-0001", "5542999990001"), ("4299999 0001", "5542999990001"),
    ("554299990001", "554299990001")])
def test_normalizar_numero_poe_o_ddi_e_tira_a_pontuacao(entrada, esperado):
    assert wa.normalizar_numero(entrada) == esperado


def test_o_nono_digito_do_celular_brasileiro_vale_dos_dois_jeitos():
    assert wa.variantes("5542999990001") == {"5542999990001", "554299990001"}
    assert wa.variantes("554299990001") == {"554299990001", "5542999990001"}
    r = roteador(autorizados=("5542999990001",))
    assert r.tratar(["554299990001"], "oi").motivo == "ok"            # o WhatsApp entregou sem o 9


def test_autorizar_valida_grava_e_remover_tira_inclusive_a_outra_forma_do_numero(tmp_path):
    arq = tmp_path / "cfg.json"
    with pytest.raises(ValueError):
        wa.autorizar("123", arquivo=arq)
    assert wa.autorizar("(42) 99999-0001", "Gustavo", arq) == "5542999990001"
    assert wa.ler_config(arq) == {"autorizados": ["5542999990001"], "nomes": {"5542999990001": "Gustavo"}}
    assert wa.remover("554299990001", arq) and wa.ler_config(arq)["autorizados"] == []
    assert not wa.remover("5542999990001", arq)                     # já não estava


def test_config_corrompida_volta_a_ninguem_autorizado(tmp_path):
    arq = tmp_path / "cfg.json"
    arq.write_text("{isto não é json", encoding="utf-8")
    assert wa.ler_config(arq)["autorizados"] == []


# ---------------------------------------------------------------- roteador ---
def test_estranho_nao_recebe_nada_e_fica_so_no_registro_mascarado():
    r = roteador()
    saida = r.tratar(["5511988887777"], "resumo rede")
    assert saida.texto is None and saida.motivo == "nao-autorizado"
    assert r.desconhecidos == {"…7777": 1} and "5511988887777" not in str(r.desconhecidos)


def test_grupo_mensagem_propria_e_vazia_sao_ignorados_mesmo_de_numero_autorizado():
    r = roteador()
    assert r.tratar([EU], "oi", grupo=True).motivo == "grupo"
    assert r.tratar([EU], "oi", minha=True).motivo == "minha"
    assert r.tratar([EU], "   ").motivo == "vazia" and r.tratar([EU], None).motivo == "vazia"
    assert r.respostas == 0


def test_numero_autorizado_recebe_resposta_formatada_com_sugestoes_numeradas():
    s = roteador().tratar([EU], "resumo centro")
    assert s.motivo == "ok" and s.numero == EU
    assert s.texto.startswith("*📊 Resumo*\n\nvocê pediu: resumo centro")
    assert "_Responda com o número:_\n1 · 📦 Estoque\n2 · 🚨 Alertas" in s.texto


def test_responder_com_o_numero_executa_a_sugestao_da_ultima_resposta():
    pedidos = []

    def responder(c):
        pedidos.append(c)
        return Resposta("t", "m", (("📦 Estoque", "estoque centro"), ("🚨 Alertas", "alertas")))
    r = roteador(responder=responder)
    r.tratar([EU], "resumo centro")
    r.tratar([EU], "2")
    r.tratar([EU], "1")
    assert pedidos == ["resumo centro", "alertas", "estoque centro"]
    assert r.tratar(["5542988880002"], "2").motivo == "nao-autorizado"      # as opções são de cada pessoa


@pytest.mark.parametrize("texto", ["oi", "Olá!", "MENU", "bom dia", "Boa noite?"])
def test_saudacao_vira_ajuda(texto):
    pedidos = []
    roteador(responder=lambda c: pedidos.append(c) or Resposta("t", "m")).tratar([EU], texto)
    assert pedidos == ["ajuda"]


def test_pergunta_nao_entendida_e_erro_de_leitura_viram_texto_sem_derrubar_o_robo():
    def entende_pouco(c):
        raise ValueError("Não entendi. 🙂 Tente assim: resumo centro")

    def quebra(c):
        raise RuntimeError("base corrompida em C:\\segredo")
    assert "Não entendi" in roteador(responder=entende_pouco).tratar([EU], "blablabla").texto
    s = roteador(responder=quebra).tratar([EU], "resumo")
    assert "Não consegui consultar" in s.texto and "segredo" not in s.texto       # o erro interno não vaza


def test_limite_por_pessoa_segura_rajada_e_libera_depois_de_um_minuto():
    t = {"agora": 0.0}
    r = roteador(relogio=lambda: t["agora"])
    assert [r.tratar([EU], "oi").motivo for _ in range(9)] == ["ok"] * 8 + ["limite"]
    t["agora"] = 61.0
    assert r.tratar([EU], "oi").motivo == "ok"


def test_entrada_e_saida_tem_teto():
    longo = "x" * 5000
    visto = []
    r = roteador(responder=lambda c: visto.append(c) or Resposta("t", longo))
    s = r.tratar([EU], "a" * 1000)
    assert len(visto[0]) == wa.MAX_ENTRADA and len(s.texto) == wa.MAX_SAIDA and s.texto.endswith("…")


# --------------------------------------------------------- o cérebro (gate) ---
def test_so_responde_com_a_base_da_demonstracao(tmp_path, monkeypatch):
    monkeypatch.setattr(wa.base, "PASTA_DADOS", tmp_path)                 # sem SIMULADO.txt: é dado real
    with pytest.raises(ValueError, match="exclusiva da demonstração"):
        wa.responder_padrao()("resumo rede")
    s = roteador(responder=wa.responder_padrao()).tratar([EU], "resumo rede")
    assert "exclusiva da demonstração" in s.texto


# ------------------------------------------------- o evento da biblioteca ---
def evento(texto="resumo centro", estendido="", sender=EU, alt="", grupo=False, minha=False):
    jid = lambda u: SimpleNamespace(User=u)                                # noqa: E731
    return SimpleNamespace(
        Info=SimpleNamespace(MessageSource=SimpleNamespace(Sender=jid(sender), SenderAlt=jid(alt), Chat=jid(sender) if sender else jid(alt),
                                                          IsGroup=grupo, IsFromMe=minha)),
        Message=SimpleNamespace(conversation=texto, extendedTextMessage=SimpleNamespace(text=estendido)))


class ClienteFalso:
    def __init__(self):
        self.enviadas = []

    def send_message(self, para, texto):
        self.enviadas.append((para.User, texto))

    def send_chat_presence(self, *a, **k):
        pass


def servico(**kw):
    return wa.ServicoWhatsApp(roteador(**kw), avisar=lambda m: None, dormir=lambda s: None)


def test_servico_responde_ao_chat_de_quem_escreveu():
    s, c = servico(), ClienteFalso()
    s._tratar(c, evento("resumo centro"))
    assert len(c.enviadas) == 1 and c.enviadas[0][0] == EU and "você pediu: resumo centro" in c.enviadas[0][1]
    assert s.estado["respostas"] == 1


def test_servico_le_texto_de_resposta_citada_e_reconhece_numero_pelo_id_alternativo():
    s, c = servico(), ClienteFalso()
    s._tratar(c, evento(texto="", estendido="alertas", sender="123456789012345", alt=EU))   # o remetente veio como LID
    assert len(c.enviadas) == 1 and "você pediu: alertas" in c.enviadas[0][1]


def test_servico_nao_responde_a_estranho_grupo_ou_a_si_mesmo():
    s, c = servico(), ClienteFalso()
    s._tratar(c, evento(sender="5511988887777"))
    s._tratar(c, evento(grupo=True))
    s._tratar(c, evento(minha=True))
    assert c.enviadas == [] and s.estado["respostas"] == 0


def test_servico_aguenta_evento_estranho_e_falha_de_envio_sem_derrubar():
    avisos = []
    s = wa.ServicoWhatsApp(roteador(), avisar=avisos.append, dormir=lambda s_: None)
    s._tratar(ClienteFalso(), SimpleNamespace())                          # evento sem os campos esperados
    assert any("ignorada" in a for a in avisos)

    class Quebrado(ClienteFalso):
        def send_message(self, *a):
            raise ConnectionError("rede caiu")
    s._tratar(Quebrado(), evento())
    assert "Falha ao responder" in s.estado["erro"]


def test_aviso_de_estranho_nao_mostra_o_numero_inteiro():
    avisos = []
    s = wa.ServicoWhatsApp(roteador(), avisar=avisos.append, dormir=lambda s_: None)
    s._tratar(ClienteFalso(), evento(sender="5511988887777"))
    assert any("NÃO autorizado" in a and "…7777" in a and "5511988887777" not in a for a in avisos)


# ------------------------------------------------------------ página do QR ---
def test_pagina_do_qr_mostra_conectando_ou_conectado_e_escapa_o_erro():
    """Sem o `segno` (a nuvem não instala o neonize, que o traz): só o desenho do QR o exige."""
    sem = wa.pagina_qr({"conectado": False, "qr": b""}, [])
    ok = wa.pagina_qr({"conectado": True, "qr": b"x"}, [EU])
    assert "Conectando" in sem
    assert "Conectado" in ok and "<svg" not in ok
    assert "&lt;script&gt;" in wa.pagina_qr({"erro": "<script>x</script>"}, [])


def test_pagina_do_qr_desenha_o_qr():
    pytest.importorskip("segno")
    com = wa.pagina_qr({"conectado": False, "qr": b"https://wa.me/settings/linked_devices#2@abc"}, [])
    assert "<svg" in com and "Aparelhos conectados" in com


# --------------------------------------------- remetente por ID interno (LID) ---
def evento_lid(lid="123456789012345", texto="resumo centro"):
    e = evento(texto=texto, sender=lid)
    e.Info.MessageSource.Sender.Server = "lid"
    return e


class ClienteComLid(ClienteFalso):
    def __init__(self, tabela):
        super().__init__()
        self.tabela = tabela

    def get_pn_from_lid(self, jid):
        if jid.User not in self.tabela:
            raise RuntimeError("não achei")
        return SimpleNamespace(User=self.tabela[jid.User])


def test_remetente_por_lid_e_resolvido_para_o_telefone_pela_sessao():
    s, c = servico(), ClienteComLid({"123456789012345": EU})
    s._tratar(c, evento_lid())
    assert len(c.enviadas) == 1 and c.enviadas[0][0] == "123456789012345"       # responde ao chat de quem escreveu (o LID)


def test_lid_sem_telefone_continua_ignorado_e_o_log_explica_o_motivo():
    avisos = []
    s = wa.ServicoWhatsApp(roteador(), avisar=avisos.append, dormir=lambda s_: None)
    c = ClienteComLid({})
    s._tratar(c, evento_lid())
    assert c.enviadas == []
    assert any("NÃO autorizado" in a and "ID interno (LID)" in a and "…2345" in a and "123456789012345" not in a for a in avisos)


def test_lid_de_estranho_resolvido_para_telefone_fora_da_lista_continua_ignorado():
    avisos = []
    s = wa.ServicoWhatsApp(roteador(), avisar=avisos.append, dormir=lambda s_: None)
    c = ClienteComLid({"123456789012345": "5511977776666"})
    s._tratar(c, evento_lid())
    assert c.enviadas == [] and any("…6666" in a and "telefone" in a for a in avisos)


# ------------------------------------- servidor: ambiente, modo mudo, dois aparelhos ---
def test_autorizados_do_ambiente_so_entram_quando_pedido_e_nunca_vao_para_o_arquivo(tmp_path, monkeypatch):
    arq = tmp_path / "cfg.json"
    wa.autorizar("(42) 99999-0001", arquivo=arq)
    monkeypatch.setenv("B2_WHATSAPP_AUTORIZADOS", "42 98888-0002, 5542977770003;lixo")
    assert wa.ler_config(arq)["autorizados"] == ["5542999990001"]                       # o arquivo não mistura o ambiente
    assert wa.ler_config(arq, ambiente=True)["autorizados"] == ["5542977770003", "5542988880002", "5542999990001"]
    wa.autorizar("42 96666-0004", arquivo=arq)                                         # gravar não leva o que veio do ambiente
    assert "5542988880002" not in arq.read_text(encoding="utf-8")


def test_modo_mudo_escuta_mas_nao_responde_para_nao_dobrar_a_resposta_com_outro_aparelho():
    avisos = []
    s = wa.ServicoWhatsApp(roteador(), avisar=avisos.append, dormir=lambda s_: None, mudo=True)
    c = ClienteFalso()
    s._tratar(c, evento("resumo centro"))
    assert c.enviadas == [] and any("(mudo)" in a and "NÃO respondi" in a for a in avisos)
    ativo = servico()
    ativo._tratar(c, evento("resumo centro"))
    assert len(c.enviadas) == 1                                                       # sem o mudo, responde normalmente
