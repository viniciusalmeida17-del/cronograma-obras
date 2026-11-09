"""Gravação da importação num banco SQLite local."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import closing
from typing import Any

from .banco_etapa4 import ESQUEMA_ETAPA4, MaoDeObraMixin
from .banco_etapa5 import ESQUEMA_ETAPA5, CronogramaMixin

ESQUEMA = """
CREATE TABLE IF NOT EXISTS obras (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                TEXT,
    prazo_valor         REAL NOT NULL,
    prazo_unidade       TEXT,
    bdi                 REAL,
    desoneracao         TEXT,
    referencias         TEXT,            -- lista JSON
    total_planilha      REAL,
    total_bdi_planilha  REAL,
    soma_servicos       REAL,
    soma_servicos_bdi   REAL,
    arquivo             TEXT,
    aba                 TEXT,
    linha_cabecalho     INTEGER,
    colunas             TEXT,            -- mapeamento JSON campo -> letra
    data_importacao     TEXT,
    arquivo_salvo       TEXT,            -- cópia do .xlsx (etapa 4 lê as composições dele)
    composicoes_abas    TEXT             -- JSON: abas onde foram achadas composições
);

CREATE TABLE IF NOT EXISTS grupos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id             INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    linha_excel         INTEGER,
    item                TEXT NOT NULL,
    descricao           TEXT,
    item_pai            TEXT,
    total_planilha      REAL,
    total_bdi_planilha  REAL,
    UNIQUE (obra_id, item)
);

CREATE TABLE IF NOT EXISTS servicos (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    linha_excel           INTEGER,
    item                  TEXT,
    item_grupo            TEXT,
    base                  TEXT,
    codigo                TEXT,
    descricao             TEXT,
    unidade               TEXT,
    quantidade            REAL,
    preco_unit            REAL,
    preco_unit_bdi        REAL,
    total                 REAL,
    total_bdi             REAL,
    natureza              TEXT NOT NULL,
    atividade_biblioteca  TEXT,
    status_ligacao        TEXT,            -- automatico, memoria, confirmado, ambiguo, sem_regra
    regra_usada           INTEGER,         -- número (ordem) da regra da biblioteca
    origem_horas          TEXT,            -- etapa 4: composicao, banco, estimado, manual, sem_mao_de_obra
    -- previstos para as próximas etapas
    etapa_obra            TEXT,
    local                 TEXT
);

-- Escolhas do usuário, reaproveitadas nas próximas obras (etapa 3)
CREATE TABLE IF NOT EXISTS memoria_ligacoes (
    base                  TEXT NOT NULL,
    codigo                TEXT NOT NULL,
    grupo                 TEXT NOT NULL,   -- nome do grupo imediato, normalizado
    atividade             TEXT NOT NULL,
    data                  TEXT NOT NULL,
    PRIMARY KEY (base, codigo, grupo)
);

-- Cópia das atividades e da sequência de cada obra (não muda se a biblioteca for editada)
CREATE TABLE IF NOT EXISTS obra_atividades (
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    codigo                TEXT NOT NULL,
    nome                  TEXT,
    etapa                 TEXT,
    tipo                  TEXT NOT NULL,
    tipo_biblioteca       TEXT,
    total_bdi             REAL,
    total                 REAL,
    n_itens               INTEGER,
    periodo_de            TEXT,
    periodo_ate           TEXT,
    equipe_principal      TEXT,
    observacao            TEXT,
    ordem_biblioteca      INTEGER,
    editada               INTEGER DEFAULT 0,
    execucao_padrao       TEXT,
    equipe_padrao         INTEGER,
    equipe_max            INTEGER,
    duracao_fixa_dias     INTEGER,
    tipo_producao         TEXT,
    PRIMARY KEY (obra_id, codigo)
);

CREATE TABLE IF NOT EXISTS obra_dependencias (
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    atividade             TEXT NOT NULL,
    depende_de            TEXT NOT NULL,
    espera_dias           INTEGER NOT NULL DEFAULT 0,
    tipo                  TEXT NOT NULL DEFAULT 'TI',  -- TI término-início, II início-início
    unidade               TEXT NOT NULL DEFAULT 'd',   -- d corridos, du úteis
    origem                TEXT,            -- biblioteca, herdada, fim, usuario
    PRIMARY KEY (obra_id, atividade, depende_de)
);

CREATE INDEX IF NOT EXISTS ix_servicos_obra ON servicos(obra_id);
CREATE INDEX IF NOT EXISTS ix_grupos_obra ON grupos(obra_id);
"""

COLUNAS_SERVICO = (
    "linha_excel", "item", "item_grupo", "base", "codigo", "descricao", "unidade",
    "quantidade", "preco_unit", "preco_unit_bdi", "total", "total_bdi", "natureza",
    "atividade_biblioteca", "status_ligacao", "regra_usada", "etapa_obra", "local",
)
COLUNAS_OBRA_ATIVIDADE = (
    "codigo", "nome", "etapa", "tipo", "tipo_biblioteca", "total_bdi", "total", "n_itens",
    "periodo_de", "periodo_ate", "equipe_principal", "observacao", "ordem_biblioteca", "editada",
    "execucao_padrao", "equipe_padrao", "equipe_max", "duracao_fixa_dias", "tipo_producao",
)
# Colunas acrescentadas depois da etapa 2 (migração de bancos antigos)
MIGRACOES = {
    "servicos": {"status_ligacao": "TEXT", "regra_usada": "INTEGER", "origem_horas": "TEXT"},
    "obras": {"arquivo_salvo": "TEXT", "composicoes_abas": "TEXT"},
    "atividade_resumo": {"maquinas": "TEXT"},
    "atividade_execucao": {"equipe_travada": "INTEGER", "producao_dia": "REAL", "maquinas_max": "INTEGER"},
    "obra_parametros": {"volume_caminhao": "REAL", "caminhoes_dia": "REAL", "juntar": "TEXT"},
    "obra_calendario": {"transferiveis": "TEXT", "min_semanas_reducao": "INTEGER", "custo_troca": "REAL",
                        "salarios": "TEXT", "encargos": "REAL", "indiretos_reais": "TEXT", "terceirizados": "TEXT",
                        "criterios": "TEXT", "maquinas_max": "INTEGER", "dividir_terceirizadas": "INTEGER"},
    "cenarios": {"receita_variavel": "REAL", "resultado": "REAL"},
    "cenario_atividades": {"maquinas": "TEXT", "partes": "TEXT"},
    "cenario_equipe_semana": {"horas_feriado": "REAL"},
    "obra_atividades": {"execucao_padrao": "TEXT", "equipe_padrao": "INTEGER", "equipe_max": "INTEGER",
                        "duracao_fixa_dias": "INTEGER", "tipo_producao": "TEXT"},
    "obra_dependencias": {"tipo": "TEXT NOT NULL DEFAULT 'TI'", "unidade": "TEXT NOT NULL DEFAULT 'd'"},
}
COLUNAS_GRUPO = ("linha_excel", "item", "descricao", "item_pai", "total_planilha", "total_bdi_planilha")


class Banco(MaoDeObraMixin, CronogramaMixin):
    def __init__(self, caminho: str):
        self.caminho = caminho
        self.pasta_arquivos = Path(caminho).resolve().parent / "arquivos_obras"
        with closing(self._conectar()) as con, con:
            for tabela, colunas in MIGRACOES.items():
                existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabela})")}
                if existentes:
                    for coluna, tipo in colunas.items():
                        if coluna not in existentes:
                            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            con.executescript(ESQUEMA)
            con.executescript(ESQUEMA_ETAPA4)
            con.executescript(ESQUEMA_ETAPA5)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.caminho)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def salvar_importacao(self, resultado: dict[str, Any]) -> int:
        """Grava obra, grupos e serviços. Retorna o id da obra."""
        obra = resultado["obra"]
        if not obra.get("prazo_valor") or obra["prazo_valor"] <= 0:
            raise ValueError("O prazo da obra é obrigatório.")
        validacao = resultado.get("validacao") or {}
        with closing(self._conectar()) as con, con:
            cur = con.execute(
                """INSERT INTO obras (nome, prazo_valor, prazo_unidade, bdi, desoneracao, referencias,
                       total_planilha, total_bdi_planilha, soma_servicos, soma_servicos_bdi,
                       arquivo, aba, linha_cabecalho, colunas, data_importacao)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    obra.get("nome"), obra["prazo_valor"], obra.get("prazo_unidade"), obra.get("bdi"),
                    obra.get("desoneracao"), json.dumps(obra.get("referencias") or [], ensure_ascii=False),
                    obra.get("total_planilha"), obra.get("total_bdi_planilha"),
                    validacao.get("soma_servicos"), validacao.get("soma_servicos_bdi"),
                    obra.get("arquivo") or resultado.get("arquivo"), resultado.get("aba"),
                    resultado.get("linha_cabecalho"), json.dumps(resultado.get("colunas") or {}),
                    obra.get("data_importacao"),
                ),
            )
            obra_id = cur.lastrowid
            con.executemany(
                f"INSERT INTO grupos (obra_id, {', '.join(COLUNAS_GRUPO)}) VALUES (?{', ?' * len(COLUNAS_GRUPO)})",
                [(obra_id, *(g.get(c) for c in COLUNAS_GRUPO)) for g in resultado["grupos"]],
            )
            con.executemany(
                f"INSERT INTO servicos (obra_id, {', '.join(COLUNAS_SERVICO)}) VALUES (?{', ?' * len(COLUNAS_SERVICO)})",
                [(obra_id, *(s.get(c) for c in COLUNAS_SERVICO)) for s in resultado["servicos"]],
            )
        return obra_id

    def listar_obras(self) -> list[dict[str, Any]]:
        with closing(self._conectar()) as con:
            linhas = con.execute(
                """SELECT o.id, o.nome, o.arquivo, o.data_importacao, o.prazo_valor, o.prazo_unidade,
                          o.soma_servicos, (SELECT COUNT(*) FROM servicos s WHERE s.obra_id = o.id) AS qtd_servicos,
                          EXISTS (SELECT 1 FROM obra_atividades a WHERE a.obra_id = o.id) AS tem_rede
                   FROM obras o ORDER BY o.id DESC"""
            ).fetchall()
        return [dict(l) for l in linhas]

    def carregar_obra(self, obra_id: int) -> dict[str, Any] | None:
        with closing(self._conectar()) as con:
            obra = con.execute("SELECT * FROM obras WHERE id = ?", (obra_id,)).fetchone()
            if obra is None:
                return None
            obra = dict(obra)
            obra["referencias"] = json.loads(obra["referencias"] or "[]")
            obra["colunas"] = json.loads(obra["colunas"] or "{}")
            grupos = [dict(g) for g in con.execute("SELECT * FROM grupos WHERE obra_id = ? ORDER BY linha_excel", (obra_id,))]
            servicos = [dict(s) for s in con.execute("SELECT * FROM servicos WHERE obra_id = ? ORDER BY linha_excel", (obra_id,))]
        return {"obra": obra, "grupos": grupos, "servicos": servicos}

    # ------------------------------------------------------------ etapa 3: ligação

    def gravar_ligacoes(self, obra_id: int, ligacoes: list[dict[str, Any]]) -> None:
        """ligacoes: [{id, atividade_biblioteca, status_ligacao, regra_usada}]"""
        with closing(self._conectar()) as con, con:
            con.executemany(
                "UPDATE servicos SET atividade_biblioteca = ?, status_ligacao = ?, regra_usada = ? WHERE id = ? AND obra_id = ?",
                [(l["atividade_biblioteca"], l["status_ligacao"], l["regra_usada"], l["id"], obra_id) for l in ligacoes],
            )

    def carregar_memoria(self) -> dict[tuple[str, str, str], str]:
        with closing(self._conectar()) as con:
            return {(r["base"], r["codigo"], r["grupo"]): r["atividade"] for r in con.execute("SELECT * FROM memoria_ligacoes")}

    def gravar_memoria(self, chaves: list[tuple[str, str, str]], atividade: str) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        with closing(self._conectar()) as con, con:
            con.executemany(
                """INSERT INTO memoria_ligacoes (base, codigo, grupo, atividade, data) VALUES (?,?,?,?,?)
                   ON CONFLICT (base, codigo, grupo) DO UPDATE SET atividade = excluded.atividade, data = excluded.data""",
                [(*chave, atividade, agora) for chave in set(chaves)],
            )

    # ------------------------------------------------------------ etapa 3: rede da obra

    def salvar_rede(self, obra_id: int, rede: dict[str, Any]) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM obra_dependencias WHERE obra_id = ?", (obra_id,))
            con.execute("DELETE FROM obra_atividades WHERE obra_id = ?", (obra_id,))
            con.executemany(
                f"INSERT INTO obra_atividades (obra_id, {', '.join(COLUNAS_OBRA_ATIVIDADE)}) VALUES (?{', ?' * len(COLUNAS_OBRA_ATIVIDADE)})",
                [(obra_id, *(int(a[c]) if c == "editada" else a.get(c) for c in COLUNAS_OBRA_ATIVIDADE)) for a in rede["atividades"].values()],
            )
            con.executemany(
                "INSERT INTO obra_dependencias (obra_id, atividade, depende_de, espera_dias, tipo, unidade, origem)"
                " VALUES (?,?,?,?,?,?,?)",
                [(obra_id, d["atividade"], d["depende_de"], d["espera_dias"], d.get("tipo") or "TI",
                  d.get("unidade") or "d", d["origem"]) for d in rede["dependencias"]],
            )

    def atualizar_atividade_obra(self, obra_id: int, codigo: str, **campos: Any) -> None:
        validos = {k: v for k, v in campos.items() if k in ("equipe_max", "equipe_padrao", "tipo_producao")}
        if not validos:
            return
        with closing(self._conectar()) as con, con:
            con.execute(f"UPDATE obra_atividades SET {', '.join(f'{k} = ?' for k in validos)} "
                        "WHERE obra_id = ? AND codigo = ?", (*validos.values(), obra_id, codigo))

    def carregar_rede(self, obra_id: int) -> dict[str, Any] | None:
        with closing(self._conectar()) as con:
            ativs = con.execute("SELECT * FROM obra_atividades WHERE obra_id = ? ORDER BY ordem_biblioteca", (obra_id,)).fetchall()
            if not ativs:
                return None
            deps = con.execute("SELECT * FROM obra_dependencias WHERE obra_id = ?", (obra_id,)).fetchall()
        atividades = {}
        for a in ativs:
            a = dict(a)
            a.pop("obra_id")
            a["editada"] = bool(a["editada"])
            atividades[a["codigo"]] = a
        dependencias = [{k: d[k] for k in ("atividade", "depende_de", "espera_dias", "tipo", "unidade", "origem")}
                        for d in deps]
        return {"atividades": atividades, "dependencias": dependencias}

    def excluir_obra(self, obra_id: int) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM obras WHERE id = ?", (obra_id,))
