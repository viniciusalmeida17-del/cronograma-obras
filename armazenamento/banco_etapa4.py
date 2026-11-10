"""Tabelas e métodos da etapa 4 (mão de obra e duração). Misturado na classe Banco."""
from __future__ import annotations

import json
import shutil
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from leitor_planilha.texto import normalizar

ESQUEMA_ETAPA4 = """
CREATE TABLE IF NOT EXISTS obra_parametros (
    obra_id               INTEGER PRIMARY KEY REFERENCES obras(id) ON DELETE CASCADE,
    horas_semana          REAL NOT NULL DEFAULT 44,
    dias_semana           INTEGER NOT NULL DEFAULT 5,
    rendimento            REAL NOT NULL DEFAULT 0.9,
    mudancas_jornada      TEXT,               -- JSON: [{"a_partir_de": "AAAA-MM-DD", "horas_semana": 42}]
    volume_caminhao       REAL,               -- etapa 5.1: m³ por caminhão de concreto (padrão 8)
    caminhoes_dia         REAL,               -- etapa 5.1: caminhões de concreto por dia (padrão 3)
    juntar                TEXT                -- etapa 5.1: JSON funcao -> destino; NULL = padrão da funcoes.xlsx
);

CREATE TABLE IF NOT EXISTS servico_mao_de_obra (
    servico_id            INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    funcao                TEXT NOT NULL,
    horas_un              REAL NOT NULL,      -- horas por unidade do serviço (bruto, sem rendimento)
    origem                TEXT NOT NULL,      -- composicao, banco, estimado, manual
    PRIMARY KEY (servico_id, funcao, origem)
);

CREATE TABLE IF NOT EXISTS servico_equipamento (
    servico_id            INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    equipamento           TEXT NOT NULL,
    horas_un              REAL NOT NULL,      -- CHP + CHI por unidade do serviço
    PRIMARY KEY (servico_id, equipamento)
);

CREATE TABLE IF NOT EXISTS servico_equipe_indireta (
    servico_id            INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    funcao                TEXT NOT NULL,
    pessoas_mes           REAL NOT NULL,
    PRIMARY KEY (servico_id, funcao)
);

CREATE TABLE IF NOT EXISTS subcomposicoes_pendentes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    servico_id            INTEGER NOT NULL REFERENCES servicos(id) ON DELETE CASCADE,
    codigo                TEXT,
    descricao             TEXT,
    unidade               TEXT,
    coeficiente           REAL,
    total_linha           REAL,               -- R$ por unidade do serviço
    horas_estimadas       REAL,
    via                   TEXT                -- JSON: códigos das subcomposições pelo caminho
);

CREATE TABLE IF NOT EXISTS atividade_execucao (
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    atividade             TEXT NOT NULL,
    execucao              TEXT,               -- propria, terceirizada; NULL = ainda não respondida
    rendimento            REAL,               -- opcional: substitui o da obra
    equipe_padrao         INTEGER,            -- opcional: substitui o da biblioteca
    duracao_manual        INTEGER,            -- opcional: dias úteis
    equipe_travada        INTEGER,            -- etapa 5: pessoas da função principal (opcional)
    producao_dia          REAL,               -- etapa 5.1: terceirizada, produção por dia (duração = qtd ÷ produção)
    maquinas_max          INTEGER,            -- etapa 5.1: máximo de máquinas de cada equipamento (padrão 6)
    PRIMARY KEY (obra_id, atividade)
);

CREATE TABLE IF NOT EXISTS atividade_equipamento (
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    atividade             TEXT NOT NULL,
    equipamento           TEXT NOT NULL,
    quantidade            INTEGER NOT NULL,   -- máquinas na obra ao mesmo tempo (padrão 1, sem linha)
    PRIMARY KEY (obra_id, atividade, equipamento)
);

CREATE TABLE IF NOT EXISTS atividade_resumo (
    obra_id               INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    atividade             TEXT NOT NULL,
    execucao              TEXT,
    funcao_principal      TEXT,
    horas_brutas          TEXT,               -- JSON funcao -> horas
    horas_ajustadas       TEXT,               -- JSON funcao -> horas
    horas_equipamento     TEXT,               -- JSON equipamento -> horas
    equipe                TEXT,               -- JSON funcao -> pessoas (equipe padrão)
    maquinas              TEXT,               -- JSON equipamento -> quantidade de máquinas
    duracao_dias          INTEGER,
    duracao_unidade       TEXT,               -- uteis ou corridos
    duracao_tipo          TEXT,               -- calculada, fixa, manual
    PRIMARY KEY (obra_id, atividade)
);

-- produção por dia digitada (terceirizadas), padrão para as próximas obras
CREATE TABLE IF NOT EXISTS producao_padrao (
    atividade             TEXT PRIMARY KEY,
    producao_dia          REAL NOT NULL,
    unidade               TEXT,
    data                  TEXT NOT NULL
);

-- Banco de coeficientes: não é apagado com a obra (sem chave estrangeira de propósito)
CREATE TABLE IF NOT EXISTS banco_coeficientes (
    base                  TEXT NOT NULL,      -- normalizado ('' quando desconhecida)
    codigo                TEXT NOT NULL,      -- normalizado
    funcao                TEXT NOT NULL,
    horas_un              REAL NOT NULL,
    obra_origem           INTEGER,
    data                  TEXT NOT NULL,
    origem                TEXT NOT NULL,      -- planilha, manual ou sinapi
    descricao             TEXT,
    PRIMARY KEY (base, codigo, funcao, origem)
);
"""

PARAMETROS_PADRAO = {"horas_semana": 44.0, "dias_semana": 5, "rendimento": 0.9, "mudancas_jornada": [],
                     "volume_caminhao": 8.0, "caminhoes_dia": 3.0, "juntar": None}


def chave(texto: Any) -> str:
    return normalizar(texto).replace(" ", "")


class BancoCoeficientes:
    """Consulta em memória do banco de coeficientes (manual → planilha → SINAPI importado)."""

    def __init__(self, linhas: list[dict[str, Any]]):
        # conjuntos completos: (base, codigo, origem) -> {funcao: h}, com a data da gravação
        conjuntos: dict[tuple[str, str, str], dict[str, Any]] = {}
        for l in linhas:
            c = conjuntos.setdefault((l["base"], l["codigo"], l["origem"]), {"data": l["data"], "horas": {}})
            c["horas"][l["funcao"]] = l["horas_un"]
            c["data"] = max(c["data"], l["data"])
        self.por_base: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
        self.por_codigo: dict[str, dict[str, dict[str, float]]] = {}
        # o mais recente vence; na busca só por código, fica o conjunto inteiro de uma base (não mistura)
        for (base, codigo, origem), c in sorted(conjuntos.items(), key=lambda x: x[1]["data"]):
            self.por_base.setdefault((base, codigo), {})[origem] = c["horas"]
            self.por_codigo.setdefault(codigo, {})[origem] = c["horas"]

    @staticmethod
    def _escolher(origens: dict[str, dict[str, float]] | None) -> dict[str, float] | None:
        if not origens:
            return None
        valores = origens.get("manual") or origens.get("planilha") or origens.get("sinapi")
        return {f: h for f, h in (valores or {}).items() if h} or None

    def buscar(self, base: Any, codigo: Any) -> dict[str, float] | None:
        if not chave(codigo):
            return None
        return self._escolher(self.por_base.get((chave(base), chave(codigo))))

    def buscar_codigo(self, codigo: Any) -> dict[str, float] | None:
        if not chave(codigo):
            return None
        return self._escolher(self.por_codigo.get(chave(codigo)))


class MaoDeObraMixin:
    # ------------------------------------------------------------------ arquivo da planilha

    def guardar_arquivo(self, obra_id: int, origem: str | Path, nome: str | None = None) -> Path:
        """Guarda uma cópia do .xlsx da obra (as composições são lidas dele na etapa 4)."""
        self.pasta_arquivos.mkdir(parents=True, exist_ok=True)
        destino = self.pasta_arquivos / f"obra_{obra_id}.xlsx"
        shutil.copyfile(origem, destino)
        with closing(self._conectar()) as con, con:
            con.execute("UPDATE obras SET arquivo_salvo = ? WHERE id = ?", (str(destino), obra_id))
        return destino

    def arquivo_da_obra(self, obra_id: int) -> Path | None:
        with closing(self._conectar()) as con:
            r = con.execute("SELECT arquivo_salvo FROM obras WHERE id = ?", (obra_id,)).fetchone()
        if r and r["arquivo_salvo"] and Path(r["arquivo_salvo"]).exists():
            return Path(r["arquivo_salvo"])
        return None

    def versao_funcoes(self, obra_id: int) -> dict[str, Any] | None:
        """Tabela de funções usada na última análise da obra: {"assinatura", "juntar_padrao"}; None = antes de existir."""
        with closing(self._conectar()) as con:
            r = con.execute("SELECT versao_funcoes FROM obras WHERE id = ?", (obra_id,)).fetchone()
        return json.loads(r["versao_funcoes"]) if r and r["versao_funcoes"] else None

    def gravar_versao_funcoes(self, obra_id: int, versao: dict[str, Any]) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("UPDATE obras SET versao_funcoes = ? WHERE id = ?", (json.dumps(versao, ensure_ascii=False), obra_id))

    def gravar_abas_composicoes(self, obra_id: int, abas: list[dict[str, Any]]) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("UPDATE obras SET composicoes_abas = ? WHERE id = ?", (json.dumps(abas, ensure_ascii=False), obra_id))

    # ------------------------------------------------------------------ parâmetros

    def carregar_parametros(self, obra_id: int) -> dict[str, Any]:
        with closing(self._conectar()) as con:
            r = con.execute("SELECT * FROM obra_parametros WHERE obra_id = ?", (obra_id,)).fetchone()
        if r is None:
            return dict(PARAMETROS_PADRAO)
        return {"horas_semana": r["horas_semana"], "dias_semana": r["dias_semana"], "rendimento": r["rendimento"],
                "mudancas_jornada": json.loads(r["mudancas_jornada"] or "[]"),
                "volume_caminhao": r["volume_caminhao"] or PARAMETROS_PADRAO["volume_caminhao"],
                "caminhoes_dia": r["caminhoes_dia"] or PARAMETROS_PADRAO["caminhoes_dia"],
                "juntar": json.loads(r["juntar"]) if r["juntar"] is not None else None}

    def salvar_parametros(self, obra_id: int, p: dict[str, Any]) -> None:
        with closing(self._conectar()) as con, con:
            con.execute(
                """INSERT INTO obra_parametros (obra_id, horas_semana, dias_semana, rendimento, mudancas_jornada,
                       volume_caminhao, caminhoes_dia, juntar)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT (obra_id) DO UPDATE SET horas_semana = excluded.horas_semana,
                       dias_semana = excluded.dias_semana, rendimento = excluded.rendimento,
                       mudancas_jornada = excluded.mudancas_jornada, volume_caminhao = excluded.volume_caminhao,
                       caminhoes_dia = excluded.caminhoes_dia, juntar = excluded.juntar""",
                (obra_id, p["horas_semana"], p["dias_semana"], p["rendimento"],
                 json.dumps(p.get("mudancas_jornada") or []), p.get("volume_caminhao"), p.get("caminhoes_dia"),
                 json.dumps(p["juntar"], ensure_ascii=False) if p.get("juntar") is not None else None),
            )

    # ------------------------------------------------------------------ análise por serviço

    def gravar_analises(self, obra_id: int, analises: dict[int, dict[str, Any]]) -> None:
        """Substitui mão de obra (menos a manual), equipamentos, equipe indireta e pendentes dos serviços."""
        ids = list(analises)
        with closing(self._conectar()) as con, con:
            marcas = ",".join("?" * len(ids))
            if ids:
                con.execute(f"DELETE FROM servico_mao_de_obra WHERE origem != 'manual' AND servico_id IN ({marcas})", ids)
                for tabela in ("servico_equipamento", "servico_equipe_indireta", "subcomposicoes_pendentes"):
                    con.execute(f"DELETE FROM {tabela} WHERE servico_id IN ({marcas})", ids)
            for sid, a in analises.items():
                con.execute("UPDATE servicos SET origem_horas = ? WHERE id = ?", (a["origem"], sid))
                con.executemany(
                    "INSERT OR REPLACE INTO servico_mao_de_obra (servico_id, funcao, horas_un, origem) VALUES (?,?,?,?)",
                    [(sid, h["funcao"], h["horas_un"], h["origem"]) for h in a["horas"] if h["origem"] != "manual"],
                )
                con.executemany("INSERT INTO servico_equipamento VALUES (?,?,?)",
                                [(sid, e, h) for e, h in a["equipamentos"].items()])
                con.executemany("INSERT INTO servico_equipe_indireta VALUES (?,?,?)",
                                [(sid, f, q) for f, q in a["indireta"].items()])
                con.executemany(
                    """INSERT INTO subcomposicoes_pendentes
                       (servico_id, codigo, descricao, unidade, coeficiente, total_linha, horas_estimadas, via)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    [(sid, p.get("codigo"), p.get("descricao"), p.get("unidade"), p.get("coeficiente"),
                      p.get("total_linha"), p.get("horas_estimadas"), json.dumps(p.get("via") or []))
                     for p in a["pendentes"]],
                )

    def gravar_estimativas(self, analises: dict[int, dict[str, Any]]) -> None:
        """Atualiza só as horas estimadas (dependem da execução escolhida e dos outros serviços)."""
        with closing(self._conectar()) as con, con:
            for sid, a in analises.items():
                con.execute("DELETE FROM servico_mao_de_obra WHERE servico_id = ? AND origem = 'estimado'", (sid,))
                con.executemany(
                    "INSERT OR REPLACE INTO servico_mao_de_obra (servico_id, funcao, horas_un, origem) VALUES (?,?,?,?)",
                    [(sid, h["funcao"], h["horas_un"], "estimado") for h in a["horas"] if h["origem"] == "estimado"],
                )
                for p in a["pendentes"]:
                    if p.get("id") is not None:
                        con.execute("UPDATE subcomposicoes_pendentes SET horas_estimadas = ? WHERE id = ?",
                                    (p.get("horas_estimadas"), p["id"]))

    def carregar_analises(self, obra_id: int) -> dict[int, dict[str, Any]]:
        """Análises gravadas (sem as estimadas). Vazio se a obra ainda não foi analisada."""
        with closing(self._conectar()) as con:
            servicos = con.execute("SELECT id, origem_horas FROM servicos WHERE obra_id = ?", (obra_id,)).fetchall()
            if not any(s["origem_horas"] for s in servicos):
                return {}
            res = {s["id"]: {"origem": s["origem_horas"], "horas": [], "equipamentos": {}, "pendentes": [], "indireta": {}}
                   for s in servicos}
            filtro = "servico_id IN (SELECT id FROM servicos WHERE obra_id = ?)"
            for r in con.execute(f"SELECT * FROM servico_mao_de_obra WHERE {filtro} AND origem != 'estimado'", (obra_id,)):
                res[r["servico_id"]]["horas"].append({"funcao": r["funcao"], "horas_un": r["horas_un"], "origem": r["origem"]})
            for r in con.execute(f"SELECT * FROM servico_equipamento WHERE {filtro}", (obra_id,)):
                res[r["servico_id"]]["equipamentos"][r["equipamento"]] = r["horas_un"]
            for r in con.execute(f"SELECT * FROM servico_equipe_indireta WHERE {filtro}", (obra_id,)):
                res[r["servico_id"]]["indireta"][r["funcao"]] = r["pessoas_mes"]
            for r in con.execute(f"SELECT * FROM subcomposicoes_pendentes WHERE {filtro} ORDER BY id", (obra_id,)):
                p = dict(r)
                p["via"] = json.loads(p["via"] or "[]")
                res[r["servico_id"]]["pendentes"].append(p)
        for a in res.values():
            if a["origem"] == "estimado" and not a["pendentes"]:
                a["estimar_servico_inteiro"] = True
        return res

    def horas_manuais(self, obra_id: int) -> dict[int, dict[str, float]]:
        with closing(self._conectar()) as con:
            linhas = con.execute(
                """SELECT m.* FROM servico_mao_de_obra m JOIN servicos s ON s.id = m.servico_id
                   WHERE s.obra_id = ? AND m.origem = 'manual'""", (obra_id,)).fetchall()
        res: dict[int, dict[str, float]] = {}
        for l in linhas:
            res.setdefault(l["servico_id"], {})[l["funcao"]] = l["horas_un"]
        return res

    def gravar_horas_manuais(self, servico_id: int, horas: dict[str, float]) -> None:
        """Substitui as horas manuais do serviço (vazio = volta ao cálculo automático)."""
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM servico_mao_de_obra WHERE servico_id = ? AND origem = 'manual'", (servico_id,))
            con.executemany("INSERT INTO servico_mao_de_obra (servico_id, funcao, horas_un, origem) VALUES (?,?,?,'manual')",
                            [(servico_id, f, h) for f, h in horas.items() if h and h > 0])

    # ------------------------------------------------------------------ execução e resumo

    def carregar_execucao(self, obra_id: int) -> dict[str, dict[str, Any]]:
        with closing(self._conectar()) as con:
            linhas = con.execute("SELECT * FROM atividade_execucao WHERE obra_id = ?", (obra_id,)).fetchall()
            maquinas = con.execute("SELECT * FROM atividade_equipamento WHERE obra_id = ?", (obra_id,)).fetchall()
        res = {l["atividade"]: {k: l[k] for k in ("execucao", "rendimento", "equipe_padrao", "duracao_manual",
                                                   "producao_dia", "maquinas_max")} for l in linhas}
        for m in maquinas:
            res.setdefault(m["atividade"], {}).setdefault("maquinas", {})[m["equipamento"]] = m["quantidade"]
        return res

    def gravar_maquinas(self, obra_id: int, atividade: str, maquinas: dict[str, int]) -> None:
        """Quantidade de máquinas por equipamento da atividade (1 = padrão, não precisa de linha)."""
        with closing(self._conectar()) as con, con:
            for equip, n in maquinas.items():
                con.execute("DELETE FROM atividade_equipamento WHERE obra_id = ? AND atividade = ? AND equipamento = ?",
                            (obra_id, atividade, equip))
                if n and n != 1:
                    con.execute("INSERT INTO atividade_equipamento VALUES (?,?,?,?)", (obra_id, atividade, equip, n))

    def iniciar_execucao(self, obra_id: int, padroes: dict[str, str | None]) -> None:
        """Cria a linha de execução das atividades que ainda não têm (não mexe nas existentes)."""
        with closing(self._conectar()) as con, con:
            con.executemany("INSERT OR IGNORE INTO atividade_execucao (obra_id, atividade, execucao) VALUES (?,?,?)",
                            [(obra_id, c, e) for c, e in padroes.items()])

    def atualizar_execucao(self, obra_id: int, atividade: str, **campos: Any) -> None:
        validos = {k: v for k, v in campos.items() if k in ("execucao", "rendimento", "equipe_padrao", "duracao_manual",
                                                            "producao_dia", "maquinas_max")}
        if not validos:
            return
        with closing(self._conectar()) as con, con:
            con.execute("INSERT OR IGNORE INTO atividade_execucao (obra_id, atividade) VALUES (?,?)", (obra_id, atividade))
            con.execute(f"UPDATE atividade_execucao SET {', '.join(f'{k} = ?' for k in validos)} WHERE obra_id = ? AND atividade = ?",
                        (*validos.values(), obra_id, atividade))

    def gravar_resumo_atividades(self, obra_id: int, atividades: list[dict[str, Any]]) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM atividade_resumo WHERE obra_id = ?", (obra_id,))
            con.executemany(
                """INSERT INTO atividade_resumo (obra_id, atividade, execucao, funcao_principal, horas_brutas,
                       horas_ajustadas, horas_equipamento, equipe, maquinas, duracao_dias, duracao_unidade, duracao_tipo)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(obra_id, a["codigo"], a["execucao"], a["funcao_principal"],
                  json.dumps(a["horas_brutas"], ensure_ascii=False), json.dumps(a["horas_ajustadas"], ensure_ascii=False),
                  json.dumps(a["horas_equipamento"], ensure_ascii=False),
                  json.dumps((a["calculo"] or {}).get("equipe") or {}, ensure_ascii=False),
                  json.dumps((a["calculo"] or {}).get("maquinas") or {}, ensure_ascii=False),
                  (a["duracao"] or {}).get("dias"), (a["duracao"] or {}).get("unidade"), (a["duracao"] or {}).get("tipo"))
                 for a in atividades],
            )

    def carregar_resumo_atividades(self, obra_id: int) -> list[dict[str, Any]]:
        with closing(self._conectar()) as con:
            linhas = con.execute("SELECT * FROM atividade_resumo WHERE obra_id = ?", (obra_id,)).fetchall()
        res = []
        for l in linhas:
            d = dict(l)
            for k in ("horas_brutas", "horas_ajustadas", "horas_equipamento", "equipe", "maquinas"):
                d[k] = json.loads(d[k] or "{}")
            res.append(d)
        return res

    def producao_padrao(self) -> dict[str, dict[str, Any]]:
        with closing(self._conectar()) as con:
            return {r["atividade"]: dict(r) for r in con.execute("SELECT * FROM producao_padrao")}

    def lembrar_producao(self, atividade: str, producao: float, unidade: str | None) -> None:
        with closing(self._conectar()) as con, con:
            con.execute("INSERT OR REPLACE INTO producao_padrao VALUES (?,?,?,?)",
                        (atividade, producao, unidade, datetime.now().isoformat(timespec="seconds")))

    # ------------------------------------------------------------------ banco de coeficientes

    def consulta_coeficientes(self) -> BancoCoeficientes:
        with closing(self._conectar()) as con:
            return BancoCoeficientes([dict(r) for r in con.execute("SELECT * FROM banco_coeficientes")])

    def gravar_coeficientes(self, base: Any, codigo: Any, horas: dict[str, float], origem: str,
                            obra_id: int | None = None, descricao: str | None = None) -> None:
        """Substitui o conjunto de funções de (base, código, origem)."""
        agora = datetime.now().isoformat(timespec="microseconds")
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM banco_coeficientes WHERE base = ? AND codigo = ? AND origem = ?",
                        (chave(base), chave(codigo), origem))
            con.executemany(
                "INSERT INTO banco_coeficientes VALUES (?,?,?,?,?,?,?,?)",
                [(chave(base), chave(codigo), f, h, obra_id, agora, origem, descricao) for f, h in horas.items() if h > 0],
            )

    def gravar_coeficientes_lote(self, base: str, composicoes: dict[str, dict[str, float]], origem: str,
                                 descricao: str | None = None) -> int:
        """Grava muitas composições de uma vez (importação do SINAPI). Retorna quantas."""
        agora = datetime.now().isoformat(timespec="microseconds")
        with closing(self._conectar()) as con, con:
            con.execute("DELETE FROM banco_coeficientes WHERE base = ? AND origem = ?", (chave(base), origem))
            con.executemany(
                "INSERT INTO banco_coeficientes VALUES (?,?,?,?,?,?,?,?)",
                [(chave(base), chave(cod), f, h, None, agora, origem, descricao)
                 for cod, horas in composicoes.items() for f, h in horas.items() if h > 0],
            )
        return len(composicoes)

    def listar_coeficientes(self, codigo: Any = None) -> list[dict[str, Any]]:
        with closing(self._conectar()) as con:
            if codigo is None:
                return [dict(r) for r in con.execute("SELECT * FROM banco_coeficientes ORDER BY codigo, funcao")]
            return [dict(r) for r in con.execute("SELECT * FROM banco_coeficientes WHERE codigo = ? ORDER BY funcao",
                                                 (chave(codigo),))]
