"""Gravação da importação num banco SQLite local."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

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
    data_importacao     TEXT
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
    -- previstos para as próximas etapas
    atividade_biblioteca  TEXT,
    etapa_obra            TEXT,
    local                 TEXT
);

CREATE INDEX IF NOT EXISTS ix_servicos_obra ON servicos(obra_id);
CREATE INDEX IF NOT EXISTS ix_grupos_obra ON grupos(obra_id);
"""

COLUNAS_SERVICO = (
    "linha_excel", "item", "item_grupo", "base", "codigo", "descricao", "unidade",
    "quantidade", "preco_unit", "preco_unit_bdi", "total", "total_bdi", "natureza",
    "atividade_biblioteca", "etapa_obra", "local",
)
COLUNAS_GRUPO = ("linha_excel", "item", "descricao", "item_pai", "total_planilha", "total_bdi_planilha")


class Banco:
    def __init__(self, caminho: str):
        self.caminho = caminho
        with closing(self._conectar()) as con, con:
            con.executescript(ESQUEMA)

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
                          o.soma_servicos, (SELECT COUNT(*) FROM servicos s WHERE s.obra_id = o.id) AS qtd_servicos
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

    def excluir_obra(self, obra_id: int) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM obras WHERE id = ?", (obra_id,))
