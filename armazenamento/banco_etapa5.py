"""Tabelas e métodos da etapa 5 (cronograma, equipes por semana, cenários). Misturado na classe Banco."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from typing import Any

ESQUEMA_ETAPA5 = """
CREATE TABLE IF NOT EXISTS servico_custo_mao_de_obra (
    servico_id            INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    funcao                TEXT NOT NULL,
    horas_un              REAL NOT NULL,      -- horas por unidade das linhas de mão de obra com preço
    custo_un              REAL NOT NULL,      -- R$ por unidade dessas linhas
    horas_un_encargos     REAL NOT NULL DEFAULT 0,  -- idem, só linhas "com encargos complementares"
    custo_un_encargos     REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (servico_id, funcao)
);

CREATE TABLE IF NOT EXISTS obra_calendario (
    obra_id               INTEGER PRIMARY KEY REFERENCES obras(id) ON DELETE CASCADE,
    data_inicio           TEXT,               -- AAAA-MM-DD (obrigatória para calcular)
    feriados_locais       TEXT,               -- JSON [{"data": "AAAA-MM-DD", "nome": "..."}]
    limite_rigidas        INTEGER NOT NULL DEFAULT 5,
    custos_hora           TEXT,               -- JSON funcao -> R$/h (valores digitados para esta obra)
    max_pessoas_total     INTEGER,            -- opcional: máximo de próprios no canteiro
    max_por_funcao        TEXT,               -- JSON funcao -> máximo (opcional)
    tempo_limite          INTEGER NOT NULL DEFAULT 60,  -- segundos por cenário
    prazos                TEXT,               -- JSON: prazos (meses) a comparar (≤ prazo da licitação)
    -- etapa 5.1
    transferiveis         TEXT,               -- JSON: funções que podem sair e voltar (NULL = Servente e Pedreiro)
    min_semanas_reducao   INTEGER,            -- cada redução dura pelo menos N semanas (padrão 2)
    custo_troca           REAL,               -- R$ por pessoa que sai ou entra (padrão 0)
    salarios              TEXT,               -- JSON funcao -> salário mensal (R$)
    encargos              REAL,               -- % de encargos sobre o salário (padrão 80)
    indiretos_reais       TEXT,               -- JSON [{descricao, valor_mes, de, ate}] (NULL = valores da planilha)
    terceirizados         TEXT,               -- JSON atividade -> valor contratado (NULL = planilha sem BDI)
    criterios             TEXT,               -- JSON item da planilha -> proporcional | mensal | fixo
    maquinas_max          INTEGER,            -- máximo de máquinas de cada equipamento por atividade (padrão 6)
    dividir_terceirizadas INTEGER             -- 1 = terceirizadas podem ser feitas em até 3 partes (padrão)
);

-- padrões lembrados para as próximas obras (salários, encargos, indiretos reais)
CREATE TABLE IF NOT EXISTS padroes_obra (
    chave                 TEXT PRIMARY KEY,
    valor                 TEXT NOT NULL,      -- JSON
    data                  TEXT NOT NULL
);
-- dias por semana e jornada ficam em obra_parametros (etapa 4)

-- último custo por hora usado, padrão para a próxima obra (não é apagado com a obra)
CREATE TABLE IF NOT EXISTS custos_hora_padrao (
    funcao                TEXT PRIMARY KEY,
    custo_hora            REAL NOT NULL,
    data                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cenarios (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    prazo_meses           REAL NOT NULL,
    data_limite           TEXT NOT NULL,
    situacao              TEXT NOT NULL,      -- otimo, melhor_encontrado, impossivel, sem_solucao
    termino               TEXT,
    pico                  INTEGER,
    homem_semana          REAL,
    ociosidade            REAL,               -- % das horas pagas sem serviço
    custo_mao_de_obra     REAL,
    custo_indiretos       REAL,
    custo_total           REAL,               -- custo real que varia com o prazo
    receita_variavel      REAL,               -- etapa 5.1: indiretas com critério mensal
    resultado             REAL,               -- receita variável − custo variável
    detalhes              TEXT,               -- JSON: menor prazo, caminho crítico, indiretos, mensagem...
    calculado_em          TEXT NOT NULL,
    segundos              REAL,
    escolhido             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cenario_atividades (
    cenario_id            INTEGER NOT NULL REFERENCES cenarios(id) ON DELETE CASCADE,
    atividade             TEXT NOT NULL,
    inicio                TEXT NOT NULL,
    termino               TEXT NOT NULL,
    modo                  TEXT,               -- JSON funcao -> pessoas
    duracao               INTEGER,
    unidade               TEXT,               -- uteis ou corridos
    folga                 INTEGER,            -- dias úteis
    critica               INTEGER,
    maquinas              TEXT,               -- JSON equipamento -> máquinas (etapa 5.1)
    partes                TEXT,               -- JSON [{inicio, termino, duracao}] (terceirizada dividida)
    PRIMARY KEY (cenario_id, atividade)
);

CREATE TABLE IF NOT EXISTS cenario_equipe_semana (
    cenario_id            INTEGER NOT NULL REFERENCES cenarios(id) ON DELETE CASCADE,
    semana                TEXT NOT NULL,      -- data da segunda-feira
    funcao                TEXT NOT NULL,
    contratados           INTEGER NOT NULL,
    horas_ocupadas        REAL NOT NULL,
    horas_pagas           REAL,
    horas_feriado         REAL,               -- etapa 5.1: horas pagas em feriado (fora da ociosidade)
    PRIMARY KEY (cenario_id, semana, funcao)
);
"""

CALENDARIO_PADRAO: dict[str, Any] = {
    "data_inicio": None, "feriados_locais": [], "limite_rigidas": 5, "custos_hora": {},
    "max_pessoas_total": None, "max_por_funcao": {}, "tempo_limite": 60, "prazos": [],
    "transferiveis": None, "min_semanas_reducao": 2, "custo_troca": 0.0, "salarios": {}, "encargos": None,
    "indiretos_reais": None, "terceirizados": {}, "criterios": {}, "maquinas_max": 6, "dividir_terceirizadas": 1,
}
_JSON = ("feriados_locais", "custos_hora", "max_por_funcao", "prazos", "transferiveis", "salarios",
         "indiretos_reais", "terceirizados", "criterios")
_PODE_SER_NULO = ("transferiveis", "indiretos_reais", "encargos", "data_inicio", "max_pessoas_total")


class CronogramaMixin:
    # ------------------------------------------------------------------ custos das composições

    def gravar_custos_mao_de_obra(self, analises: dict[int, dict[str, Any]]) -> None:
        ids = list(analises)
        with closing(self._conectar()) as con, con:
            if ids:
                con.execute(f"DELETE FROM servico_custo_mao_de_obra WHERE servico_id IN ({','.join('?' * len(ids))})", ids)
            con.executemany(
                "INSERT INTO servico_custo_mao_de_obra VALUES (?,?,?,?,?,?)",
                [(sid, f, c["horas_un"], c["custo_un"], c.get("horas_un_encargos", 0), c.get("custo_un_encargos", 0))
                 for sid, a in analises.items() for f, c in (a.get("custos_mo") or {}).items()],
            )

    def carregar_custos_mao_de_obra(self, obra_id: int) -> list[dict[str, Any]]:
        with closing(self._conectar()) as con:
            return [dict(r) for r in con.execute(
                """SELECT c.*, s.quantidade FROM servico_custo_mao_de_obra c JOIN servicos s ON s.id = c.servico_id
                   WHERE s.obra_id = ?""", (obra_id,))]

    # ------------------------------------------------------------------ parâmetros do cronograma

    def carregar_calendario(self, obra_id: int) -> dict[str, Any]:
        with closing(self._conectar()) as con:
            r = con.execute("SELECT * FROM obra_calendario WHERE obra_id = ?", (obra_id,)).fetchone()
        if r is None:
            return json.loads(json.dumps(CALENDARIO_PADRAO))
        d = {k: r[k] for k in CALENDARIO_PADRAO}
        for k in _JSON:
            if d[k]:
                d[k] = json.loads(d[k])
            else:
                d[k] = None if k in _PODE_SER_NULO else json.loads(json.dumps(CALENDARIO_PADRAO[k]))
        for k, v in CALENDARIO_PADRAO.items():
            if d[k] is None and k not in _PODE_SER_NULO:
                d[k] = v
        return d

    def salvar_calendario(self, obra_id: int, c: dict[str, Any]) -> None:
        valores = [(json.dumps(c[k], ensure_ascii=False) if c.get(k) is not None else None) if k in _JSON else c.get(k)
                   for k in CALENDARIO_PADRAO]
        with closing(self._conectar()) as con, con:
            con.execute(f"INSERT OR REPLACE INTO obra_calendario (obra_id, {', '.join(CALENDARIO_PADRAO)}) "
                        f"VALUES (?{', ?' * len(CALENDARIO_PADRAO)})", (obra_id, *valores))

    def padrao(self, chave: str) -> Any:
        with closing(self._conectar()) as con:
            r = con.execute("SELECT valor FROM padroes_obra WHERE chave = ?", (chave,)).fetchone()
        return json.loads(r["valor"]) if r else None

    def lembrar_padrao(self, chave: str, valor: Any) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("INSERT OR REPLACE INTO padroes_obra VALUES (?,?,?)",
                        (chave, json.dumps(valor, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))

    def custos_hora_padrao(self) -> dict[str, float]:
        with closing(self._conectar()) as con:
            return {r["funcao"]: r["custo_hora"] for r in con.execute("SELECT * FROM custos_hora_padrao")}

    def lembrar_custos_hora(self, custos: dict[str, float]) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as con, con:
            con.executemany("INSERT OR REPLACE INTO custos_hora_padrao VALUES (?,?,?)",
                            [(f, float(v), agora) for f, v in custos.items() if v is not None])

    def travar_equipe(self, obra_id: int, atividade: str, pessoas: int | None) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("INSERT OR IGNORE INTO atividade_execucao (obra_id, atividade) VALUES (?,?)", (obra_id, atividade))
            con.execute("UPDATE atividade_execucao SET equipe_travada = ? WHERE obra_id = ? AND atividade = ?",
                        (pessoas, obra_id, atividade))

    def equipes_travadas(self, obra_id: int) -> dict[str, int]:
        with closing(self._conectar()) as con:
            return {r["atividade"]: r["equipe_travada"] for r in con.execute(
                "SELECT atividade, equipe_travada FROM atividade_execucao WHERE obra_id = ? AND equipe_travada IS NOT NULL",
                (obra_id,))}

    # ------------------------------------------------------------------ cenários

    def gravar_cenario(self, obra_id: int, prazo_meses: float, data_limite: str, res: dict[str, Any]) -> int:
        """Grava um cenário calculado (substitui o cenário anterior com o mesmo prazo)."""
        detalhes = {k: res.get(k) for k in ("menor_prazo", "caminho_critico", "indiretos", "mensagem", "origem",
                                             "limite_inferior", "horas_pagas", "horas_ocupadas", "dias_uteis",
                                             "contratados", "violacoes", "periodos_indiretas", "equipe_indireta",
                                             "receita_variavel", "resultado", "receitas", "horas_feriado",
                                             "ociosidade_funcao", "causas_ociosidade", "diagnostico", "avisos_custos",
                                             "custo_terceirizados", "partes", "maquinas")}
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as con, con:
            antes = con.execute("SELECT MAX(escolhido) FROM cenarios WHERE obra_id = ? AND prazo_meses = ?",
                                (obra_id, prazo_meses)).fetchone()[0]
            escolhido = int(bool(antes) and res["situacao"] in ("otimo", "melhor_encontrado"))
            con.execute("DELETE FROM cenarios WHERE obra_id = ? AND prazo_meses = ?", (obra_id, prazo_meses))
            cur = con.execute(
                """INSERT INTO cenarios (obra_id, prazo_meses, data_limite, situacao, termino, pico, homem_semana,
                       ociosidade, custo_mao_de_obra, custo_indiretos, custo_total, detalhes, calculado_em, segundos,
                       escolhido, receita_variavel, resultado)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (obra_id, prazo_meses, data_limite, res["situacao"], res.get("termino"), res.get("pico"),
                 res.get("homem_semana"), res.get("ociosidade"), res.get("custo_mao_de_obra"),
                 res.get("custo_indiretos"), res.get("custo_total"), json.dumps(detalhes, ensure_ascii=False),
                 agora, res.get("segundos"), escolhido, res.get("receita_variavel"), res.get("resultado")))
            cid = cur.lastrowid
            con.executemany(
                "INSERT INTO cenario_atividades (cenario_id, atividade, inicio, termino, modo, duracao, unidade, folga,"
                " critica, maquinas, partes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(cid, a["codigo"], a["inicio"], a["termino"], json.dumps(a["equipe"], ensure_ascii=False), a["duracao"],
                  a["unidade"], a["folga"], int(a["critica"]), json.dumps(a.get("maquinas") or {}, ensure_ascii=False),
                  json.dumps(a.get("partes"), ensure_ascii=False) if a.get("partes") else None)
                 for a in res.get("atividades") or []])
            con.executemany(
                "INSERT INTO cenario_equipe_semana (cenario_id, semana, funcao, contratados, horas_ocupadas, horas_pagas,"
                " horas_feriado) VALUES (?,?,?,?,?,?,?)",
                [(cid, e["semana"], e["funcao"], e["contratados"], e["horas_ocupadas"], e["horas_pagas"],
                  e.get("horas_feriado") or 0.0)
                 for e in res.get("equipe_semana") or []])
        return cid

    def listar_cenarios(self, obra_id: int) -> list[dict[str, Any]]:
        with closing(self._conectar()) as con:
            linhas = con.execute("SELECT * FROM cenarios WHERE obra_id = ? ORDER BY prazo_meses", (obra_id,)).fetchall()
        res = []
        for l in linhas:
            d = dict(l)
            d["detalhes"] = json.loads(d["detalhes"] or "{}")
            d["escolhido"] = bool(d["escolhido"])
            res.append(d)
        return res

    def carregar_cenario(self, cenario_id: int) -> dict[str, Any] | None:
        with closing(self._conectar()) as con:
            c = con.execute("SELECT * FROM cenarios WHERE id = ?", (cenario_id,)).fetchone()
            if c is None:
                return None
            d = dict(c)
            d["detalhes"] = json.loads(d["detalhes"] or "{}")
            d["escolhido"] = bool(d["escolhido"])
            d["atividades"] = []
            for r in con.execute("SELECT * FROM cenario_atividades WHERE cenario_id = ?", (cenario_id,)):
                a = dict(r)
                a["equipe"] = json.loads(a.pop("modo") or "{}")
                a["maquinas"] = json.loads(a.get("maquinas") or "{}")
                a["partes"] = json.loads(a["partes"]) if a.get("partes") else None
                a["critica"] = bool(a["critica"])
                d["atividades"].append(a)
            d["equipe_semana"] = [dict(r) for r in con.execute(
                "SELECT * FROM cenario_equipe_semana WHERE cenario_id = ? ORDER BY semana, funcao", (cenario_id,))]
        return d

    def escolher_cenario(self, obra_id: int, cenario_id: int) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("UPDATE cenarios SET escolhido = (id = ?) WHERE obra_id = ?", (cenario_id, obra_id))
