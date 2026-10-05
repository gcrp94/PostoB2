"""Menor Preço (Nota Paraná): leitura da resposta do app, coleta que PARA ao primeiro sinal de bloqueio, e as análises.

    python -m pytest tests/test_nota_parana.py

Nada aqui acessa a internet: o servidor é um `abrir` falso que devolve respostas fabricadas.
"""
from __future__ import annotations

import json
import math
import urllib.error
from datetime import datetime

import pandas as pd
import pytest

from src import nota_parana as npr

AGORA = datetime(2026, 10, 5, 8, 30)


def oferta(rua, numero, desc, valor, quando="2026-10-05T14:25:09.825Z", loja=None, razao="POSTO X LTDA",
           bairro="CENTRO", mun="GUARAPUAVA", dist="1.0"):
    return {"desc": desc, "valor": str(valor), "datahora": quando, "distkm": dist, "cdanp": "320102001",
            "estabelecimento": {"codigo": loja or f"{rua}{numero}", "nm_emp": razao, "nm_fan": "", "tp_logr": "RUA",
                                "nm_logr": rua, "nr_logr": numero, "bairro": bairro, "mun": mun, "uf": "PR"}}


def resposta(*itens, total=None):
    return {"tempo": 5, "local": "x", "produtos": list(itens), "total": total if total is not None else len(itens),
            "precos": {"min": "1", "max": "9"}}


def servidor(*respostas, status=200, tipo="application/json; charset=utf-8"):
    """Um `abrir` falso: devolve as respostas em sequência (a última se repete) e guarda as URLs pedidas."""
    pedidos = []

    def abrir(url):
        pedidos.append(url)
        r = respostas[min(len(pedidos) - 1, len(respostas) - 1)]
        corpo = r if isinstance(r, bytes) else json.dumps(r).encode()
        return status, tipo, corpo
    abrir.pedidos = pedidos
    return abrir


# ------------------------------------------------------------------ leitura ---
def test_geohash_bate_com_o_centro_de_guarapuava_e_ida_e_volta_fecha():
    assert npr.geohash(-25.3935, -51.4600).startswith("6g7rscrb")
    assert npr.geohash(-25.3935, -51.4600, 5) == "6g7rs"
    lat, lon = npr.decodificar(npr.geohash(-25.3935, -51.4600, 11))
    assert lat == pytest.approx(-25.3935, abs=1e-4) and lon == pytest.approx(-51.4600, abs=1e-4)


def test_grade_cobre_a_caixa_sem_buraco_e_todo_ponto_cai_dentro_dela():
    sul, oeste, norte, leste = npr.CAIXA_GUARAPUAVA
    pontos = [npr.decodificar(c.geohash) for c in npr.CENTROS]
    assert 9 <= len(npr.CENTROS) <= 25 and len({c.geohash for c in npr.CENTROS}) == len(npr.CENTROS)
    assert all(sul < la < norte and oeste < lo < leste for la, lo in pontos)
    # qualquer ponto da caixa fica a no máximo `raio` km de algum centro (grade de 4,5 km, raio de 4 km)
    for la in (sul, (sul + norte) / 2, norte):
        for lo in (oeste, (oeste + leste) / 2, leste):
            dist = min(math.hypot((la - pla) * 111.0, (lo - plo) * 100.4) for pla, plo in pontos)
            assert dist <= npr.RAIO_KM


@pytest.mark.parametrize("desc,tp,esperado", [
    ("GASOLINA COMUM BICO 11", 1, "Gasolina Comum"),            # o B2 Centro: cdanp de aditivada, nome de comum
    ("GASOLINA C COMUM ONU 3475", 1, "Gasolina Comum"),
    ("ORIGINAL GASOLINA BICO 02", 2, "Gasolina Comum"),         # Ipiranga "Original" aparece na busca de aditivada
    ("GASOLINA V POWER BICO 2", 1, "Gasolina Aditivada"),       # a V-Power aparece na busca de comum
    ("GASOLINA PETROBRAS PODIUM ", 1, "Gasolina Aditivada"),
    ("GA GASOLINA ADITIVADA IPIMAX", 2, "Gasolina Aditivada"),
    ("ETANOL HIDRATADO", 3, "Etanol"),
    ("OLEO DIESEL B S10 COMUM", 4, "Diesel S10"),
    ("DIESEL B S-500", 4, "Diesel S500"),
    ("GAS NATURAL VEICULAR", 5, None)])
def test_classificar_pelo_nome_da_nota_e_nao_pelo_tipo_da_busca(desc, tp, esperado):
    assert npr.classificar(desc, tp) == esperado


def test_unidade_b2_pelo_endereco_e_so_em_guarapuava():
    assert npr.unidade_b2("GUAIRA", "3148", "GUARAPUAVA") == "B2 Centro"
    assert npr.unidade_b2("SEBASTIAO DE CAMARGO RIBAS", "1071", "GUARAPUAVA") == "B2 Bonsucesso"
    assert npr.unidade_b2("MANOEL RIBAS", "2760", "GUARAPUAVA") == "B2 Índio"
    assert npr.unidade_b2("JOAO FORTKAMP", "0721", "GUARAPUAVA") == "B2 Primavera"       # zero à esquerda não atrapalha
    assert npr.unidade_b2("MANOEL RIBAS", "1877", "GUARAPUAVA") == ""                    # outro posto na mesma rua
    assert npr.unidade_b2("GUAIRA", "3148", "CANDOI") == ""


def test_normalizar_passa_a_hora_para_brasilia_e_descarta_o_que_nao_e_combustivel():
    r = resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM BICO 11", "5.69", "2026-10-05T14:25:09.825Z"),
                 oferta("RUA Y", "1", "GAS NATURAL VEICULAR", "4.00"),
                 oferta("RUA Z", "2", "GASOLINA COMUM", "0.00"),                          # preço zerado
                 {"desc": "GASOLINA COMUM", "valor": "abc", "datahora": "x", "estabelecimento": {}})   # lixo
    d = npr.normalizar(r, "Guarapuava", 1, AGORA)
    assert len(d) == 1
    linha = d.iloc[0]
    assert linha["produto"] == "Gasolina Comum" and linha["preco"] == pytest.approx(5.69)
    assert linha["datahora"] == pd.Timestamp("2026-10-05 11:25:09.825") and linha["unidade_b2"] == "B2 Centro"


# ------------------------------------------------------------------- coleta ---
def test_coleta_junta_os_tipos_e_pausa_entre_as_consultas():
    abrir = servidor(resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69")))
    pausas = []
    r = npr.coletar((npr.CENTROS[0],), (1, 3), (8, 20), abrir, pausas.append, lambda: AGORA)
    assert r.status == "ok" and r.consultas == 2 and len(abrir.pedidos) == 2
    assert len(pausas) == 1 and 8 <= pausas[0] <= 20                  # nenhuma pausa antes da 1ª; uma entre as duas
    assert "tp_comb=1" in abrir.pedidos[0] and "tp_comb=3" in abrir.pedidos[1] and "raio=4" in abrir.pedidos[0]
    assert set(r.linhas["produto"]) == {"Gasolina Comum"}              # a 2ª resposta, de "etanol", só trouxe gasolina: descartada
    assert len(r.linhas) == 1                                          # e a repetida não duplica


def test_coleta_pede_a_proxima_pagina_so_se_faltar_e_para_se_nada_for_novo():
    a, b = oferta("RUA A", "1", "GASOLINA COMUM", "5.50"), oferta("RUA B", "2", "GASOLINA COMUM", "5.60")
    abrir = servidor(resposta(a, total=3), resposta(b, total=3), resposta(b, total=3))
    r = npr.coletar((npr.CENTROS[0],), (1,), (0, 0), abrir, lambda s: None, lambda: AGORA)
    assert r.consultas == 3 and len(r.linhas) == 2 and "offset=1" in abrir.pedidos[1] and "offset=2" in abrir.pedidos[2]
    completa = servidor(resposta(a, b, total=2))
    assert npr.coletar((npr.CENTROS[0],), (1,), (0, 0), completa, lambda s: None, lambda: AGORA).consultas == 1


def test_ponto_sem_nenhum_posto_nao_pergunta_os_outros_combustiveis():
    vazio, cheio = resposta(), resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69"))
    a, b = npr.CENTROS[0], npr.CENTROS[1]
    chamadas = []

    def abrir(url):
        chamadas.append(url)
        return 200, "application/json", json.dumps(vazio if len(chamadas) == 1 else cheio).encode()
    r = npr.coletar((a, b), (1, 2, 3), (0, 0), abrir, lambda s: None, lambda: AGORA)
    assert r.consultas == 4                                    # ponto vazio: 1 consulta; ponto com posto: as 3


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_coleta_para_ao_primeiro_sinal_de_bloqueio_e_nao_insiste(status):
    abrir = servidor(b"", status=status)
    r = npr.coletar(npr.CENTROS, npr.TIPOS, (0, 0), abrir, lambda s: None, lambda: AGORA)
    assert r.status == "interrompida" and len(abrir.pedidos) == 1 and r.linhas.empty
    assert str(status) in r.mensagem


def test_coleta_para_se_a_resposta_nao_for_o_json_esperado():
    pagina = servidor(b"<html>Verifique que voce e humano</html>", tipo="text/html")
    r = npr.coletar(npr.CENTROS, npr.TIPOS, (0, 0), pagina, lambda s: None, lambda: AGORA)
    assert r.status == "interrompida" and len(pagina.pedidos) == 1 and "formato esperado" in r.mensagem
    outro = servidor({"erro": "novo formato"})
    assert npr.coletar(npr.CENTROS, npr.TIPOS, (0, 0), outro, lambda s: None, lambda: AGORA).status == "interrompida"


def test_coleta_guarda_o_que_ja_veio_quando_interrompe_no_meio():
    ok = resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69"))
    chamadas = []

    def abrir(url):
        chamadas.append(url)
        return (200, "application/json", json.dumps(ok).encode()) if len(chamadas) == 1 else (429, "", b"")
    r = npr.coletar((npr.CENTROS[0],), (1, 2), (0, 0), abrir, lambda s: None, lambda: AGORA)
    assert r.status == "interrompida" and r.consultas == 1 and len(r.linhas) == 1


def test_rede_que_oscila_tem_uma_segunda_tentativa_depois_de_uma_pausa_longa():
    chamadas, pausas = [], []

    def abrir(url):
        chamadas.append(url)
        if len(chamadas) == 1:
            raise urllib.error.URLError("sem rede")
        return 200, "application/json", json.dumps(resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69"))).encode()
    r = npr.coletar((npr.CENTROS[0],), (1,), (0, 0), abrir, pausas.append, lambda: AGORA)
    assert r.status == "ok" and len(chamadas) == 2 and pausas == [45]
    sempre = npr.coletar((npr.CENTROS[0],), (1,), (0, 0), lambda u: (_ for _ in ()).throw(urllib.error.URLError("x")),
                         lambda s: None, lambda: AGORA)
    assert sempre.status == "interrompida"


# ----------------------------------------------------------- gravar e ler ---
def test_gravar_acumula_sem_repetir_a_mesma_nota(tmp_path):
    r = resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69"), oferta("RUA B", "2", "GASOLINA COMUM", "5.80"))
    d1 = npr.normalizar(r, "G", 1, AGORA)
    assert npr.gravar(d1, tmp_path) == 2
    assert npr.gravar(d1, tmp_path) == 0                               # a mesma nota de novo não entra
    amanha = resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.79", "2026-10-06T13:00:00Z"))
    assert npr.gravar(npr.normalizar(amanha, "G", 1, AGORA), tmp_path) == 1
    assert len(npr.carregar(tmp_path)) == 3 and not list(tmp_path.glob("*.tmp"))


def test_trava_de_uma_coleta_por_dia_so_conta_coleta_que_deu_certo(tmp_path):
    ok, ruim = npr.Resultado(pd.DataFrame(columns=npr.COLUNAS), 10), npr.Resultado(pd.DataFrame(columns=npr.COLUNAS), 1, "interrompida", "HTTP 429")
    assert not npr.ja_coletou_hoje(AGORA, tmp_path)
    npr.anotar(ruim, 0, AGORA, tmp_path)
    assert not npr.ja_coletou_hoje(AGORA, tmp_path)                    # tentativa interrompida não conta
    npr.anotar(ok, 5, AGORA, tmp_path)
    assert npr.ja_coletou_hoje(AGORA, tmp_path)
    assert not npr.ja_coletou_hoje(datetime(2026, 10, 6, 8, 0), tmp_path)


# ---------------------------------------------------------------- análises ---
def ofertas_de_teste():
    linhas = []
    for dia, deslocamento in (("2026-10-05", 0.0), ("2026-10-06", 0.10)):
        itens = [("GUAIRA", "3148", 5.69), ("MANOEL RIBAS", "2760", 5.99), ("RUA A", "1", 5.89), ("RUA B", "2", 6.09),
                 ("RUA C", "3", 6.39)]
        r = resposta(*[oferta(rua, n, "GASOLINA COMUM", f"{p + deslocamento:.2f}", f"{dia}T12:00:00Z") for rua, n, p in itens],
                     *[oferta(rua, n, "GASOLINA ADITIVADA", f"{p + 0.30 + deslocamento:.2f}", f"{dia}T12:05:00Z")
                       for rua, n, p in itens[2:]],
                     oferta("GUAIRA", "3148", "GASOLINA ADITIVADA BICO 3", f"{5.69 + deslocamento:.2f}", f"{dia}T12:10:00Z"))
        linhas.append(npr.normalizar(r, "G", 1, datetime.fromisoformat(f"{dia}T08:30:00")))      # uma coleta por dia
    return pd.concat(linhas, ignore_index=True)


def test_foto_posicao_e_media_da_cidade():
    of = ofertas_de_teste()
    f = npr.foto(of, "Gasolina Comum")
    assert len(f) == 5 and f.loc["GUAIRA3148", "preco"] == pytest.approx(5.79)      # a nota mais recente de cada posto
    r = npr.resumo(f)
    assert r["n"] == 5 and r["minimo"] == pytest.approx(5.79)
    centro = next(b for b in r["b2"] if b["unidade"] == "B2 Centro")
    assert centro["posicao"] == 1 and {b["unidade"] for b in r["b2"]} == {"B2 Centro", "B2 Índio"}


def test_foto_ignora_nota_velha_demais():
    of = ofertas_de_teste()
    antiga = of[(of["loja"] == "RUA C3") & (of["datahora"] < pd.Timestamp("2026-10-06"))]
    sem_c_hoje = of.drop(of[(of["loja"] == "RUA C3") & (of["datahora"] >= pd.Timestamp("2026-10-06"))].index)
    assert len(antiga) == 2 and "RUA C3" in npr.foto(sem_c_hoje, "Gasolina Comum", horas=48).index
    assert "RUA C3" not in npr.foto(sem_c_hoje, "Gasolina Comum", horas=6).index


def test_historico_diario_traz_a_faixa_da_cidade_e_o_preco_de_cada_unidade():
    h = npr.historico_diario(ofertas_de_teste(), "Gasolina Comum")
    assert len(h) == 2 and list(h["n"]) == [5, 5]
    assert h.loc[1, "B2 Centro"] == pytest.approx(5.79) and h.loc[0, "B2 Índio"] == pytest.approx(5.99)
    assert h.loc[0, "minimo"] == pytest.approx(5.69) and h.loc[0, "maximo"] == pytest.approx(6.39)


def test_premio_da_aditivada_mostra_quem_cobra_igual():
    p = npr.premio_aditivada(ofertas_de_teste())
    assert p.loc["GUAIRA3148", "premio"] == pytest.approx(0.0)            # B2 Centro: aditivada pelo preço da comum
    assert p.loc["RUA A1", "premio"] == pytest.approx(0.30)
    assert "MANOEL RIBAS2760" not in p.index                              # sem aditivada informada: fica de fora


def test_estado_resume_o_que_ja_foi_coletado(tmp_path):
    of = ofertas_de_teste()
    npr.gravar(of, tmp_path)
    npr.anotar(npr.Resultado(of, 10), len(of), AGORA, tmp_path)
    e = npr.estado(npr.carregar(tmp_path), tmp_path)
    assert e["dias"] == 2 and e["ofertas"] == len(of) and e["ultima"] == pd.Timestamp(AGORA).floor("s") and e["interrompida"] is None
    npr.anotar(npr.Resultado(of.iloc[:0], 1, "interrompida", "HTTP 429"), 0, datetime(2026, 10, 6, 8, 0), tmp_path)
    assert "429" in npr.estado(npr.carregar(tmp_path), tmp_path)["interrompida"]["mensagem"]


def test_conferir_cadastro_diz_quem_a_varredura_achou_e_quem_nao():
    of = npr.normalizar(resposta(
        oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69", loja="a"),
        oferta("QUINZE DE NOVEMBRO", "1571", "GASOLINA COMUM", "6.39", loja="b", mun="CANDOI"),     # outro município
        oferta("MANOEL RIBAS", "2760", "GASOLINA COMUM", "5.99", loja="c", bairro="CONRADINHO"),
        oferta("XV DE NOVEMBRO", "6879", "GASOLINA COMUM", "5.59", loja="d")), "G", 1, AGORA)
    cad = pd.DataFrame([
        {"cnpj": "1", "razao": "BEGNINI LTDA", "endereco": "RUA GUAIRA, 3148", "bairro": "CENTRO", "municipio": "GUARAPUAVA", "eh_b2": True},
        {"cnpj": "2", "razao": "BEGNINI LTDA", "endereco": "AVENIDA MANOEL RIBAS, 2760", "bairro": "CONRADINHO", "municipio": "GUARAPUAVA", "eh_b2": True},
        {"cnpj": "3", "razao": "BEGNINI LTDA", "endereco": "RUA JOAO FORTKAMP, 721", "bairro": "PRIMAVERA", "municipio": "GUARAPUAVA", "eh_b2": True},
        {"cnpj": "4", "razao": "OUTRO LTDA", "endereco": "AVENIDA AV XV DE NOVEMBRO, 6879", "bairro": "CENTRO", "municipio": "GUARAPUAVA", "eh_b2": False},
        {"cnpj": "5", "razao": "B2 LTDA", "endereco": "AVENIDA AV XV DE NOVEMBRO, 1571", "bairro": "CENTRO", "municipio": "CANDOI", "eh_b2": True}])
    c = npr.conferir_cadastro(of, cad).set_index("cnpj")
    assert list(c.index) == ["1", "2", "3", "4"]                           # Candói fica de fora (outro município)
    assert dict(c["achado"]) == {"1": True, "2": True, "3": False, "4": True}
    assert c.loc["1", "loja"] == "a" and c.loc["3", "loja"] == ""


def test_dia_a_dia_usa_o_ponto_central_e_a_grade_so_na_primeira_vez_e_a_cada_30_dias(tmp_path):
    assert len(npr.CENTRO_LARGO) == 1 and npr.CENTRO_LARGO[0].raio == 8
    vazio = pd.DataFrame(columns=npr.COLUNAS)
    assert npr.precisa_varredura_completa(AGORA, tmp_path)                              # nunca varreu
    npr.anotar(npr.Resultado(vazio, 65, modo="completa"), 100, datetime(2026, 10, 5, 8, 0), tmp_path)
    npr.anotar(npr.Resultado(vazio, 5, modo="diaria"), 3, datetime(2026, 10, 6, 8, 0), tmp_path)
    assert not npr.precisa_varredura_completa(datetime(2026, 10, 20), tmp_path)         # a diária não conta como varredura
    assert npr.precisa_varredura_completa(datetime(2026, 11, 5, 8, 1), tmp_path)        # 31 dias depois
    npr.anotar(npr.Resultado(vazio, 3, "interrompida", "HTTP 429", modo="completa"), 0, datetime(2026, 11, 5, 9, 0), tmp_path)
    assert npr.precisa_varredura_completa(datetime(2026, 11, 6), tmp_path)             # varredura interrompida não vale


def test_log_antigo_sem_a_coluna_modo_continua_legivel_e_ganha_a_coluna(tmp_path):
    (tmp_path / npr.ARQ_LOG).write_text("quando,status,consultas,ofertas,novas,mensagem\n2026-10-05 11:56:39,ok,65,174,174,\n",
                                        encoding="utf-8")
    assert list(npr.ler_log(tmp_path)["modo"]) == [""]
    npr.anotar(npr.Resultado(pd.DataFrame(columns=npr.COLUNAS), 5, modo="diaria"), 2, datetime(2026, 10, 6, 8, 0), tmp_path)
    log = npr.ler_log(tmp_path)
    assert list(log["consultas"]) == [65, 5] and list(log["modo"]) == ["", "diaria"] and npr.ja_coletou_hoje(datetime(2026, 10, 6), tmp_path)


def test_a_mesma_nota_entra_de_novo_em_outro_dia_de_coleta_para_a_serie_nao_perder_postos(tmp_path):
    r = resposta(oferta("GUAIRA", "3148", "GASOLINA COMUM", "5.69"), oferta("RUA B", "2", "GASOLINA COMUM", "5.80"))
    assert npr.gravar(npr.normalizar(r, "G", 1, datetime(2026, 10, 5, 8, 30)), tmp_path) == 2
    assert npr.gravar(npr.normalizar(r, "G", 1, datetime(2026, 10, 5, 18, 0)), tmp_path) == 0      # mesmo dia: não repete
    assert npr.gravar(npr.normalizar(r, "G", 1, datetime(2026, 10, 6, 8, 30)), tmp_path) == 2      # outro dia: o app mostrou de novo
    h = npr.historico_diario(npr.carregar(tmp_path), "Gasolina Comum")
    assert list(h["n"]) == [2, 2] and list(h["dia"]) == [pd.Timestamp("2026-10-05"), pd.Timestamp("2026-10-06")]


def test_conferir_cadastro_aceita_numero_com_diferenca_de_1_ou_2_se_a_rua_for_a_mesma():
    of = npr.normalizar(resposta(oferta("PADRE CHAGAS", "3592", "GASOLINA COMUM", "5.99", loja="a")), "G", 1, AGORA)
    cad = pd.DataFrame([
        {"cnpj": "1", "razao": "DISOESTE", "endereco": "RUA PADRE CHAGAS, 3591", "bairro": "CENTRO", "municipio": "GUARAPUAVA", "eh_b2": False},
        {"cnpj": "2", "razao": "OUTRO", "endereco": "RUA PADRE CHAGAS, 2800", "bairro": "OUTRO BAIRRO", "municipio": "GUARAPUAVA", "eh_b2": False}])
    c = npr.conferir_cadastro(of, cad).set_index("cnpj")
    assert dict(c["achado"]) == {"1": True, "2": False}
