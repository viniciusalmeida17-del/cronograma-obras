"""Calendário da obra: dias úteis, feriados nacionais (fixos e móveis), feriados locais e jornada por semana."""
from __future__ import annotations

import bisect
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

FERIADOS_FIXOS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia da Consciência Negra",
    (12, 25): "Natal",
}


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> dict[date, str]:
    p = pascoa(ano)
    res = {date(ano, m, d): nome for (m, d), nome in FERIADOS_FIXOS.items()}
    res[p - timedelta(days=48)] = "Carnaval (segunda)"
    res[p - timedelta(days=47)] = "Carnaval (terça)"
    res[p - timedelta(days=2)] = "Sexta-feira Santa"
    res[p + timedelta(days=60)] = "Corpus Christi"
    return res


def para_data(valor: Any) -> date:
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor).strip()[:10])


def somar_meses(d: date, meses: int) -> date:
    ano, mes = divmod(d.month - 1 + int(meses), 12)
    ano += d.year
    mes += 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(ano, mes, min(d.day, dia))
        except ValueError:
            continue
    raise ValueError(d)


def data_limite(inicio: date, meses: float) -> date:
    """Último dia do prazo: início + N meses − 1 dia (meses fracionários: 30,4375 dias por mês)."""
    if float(meses) == int(meses):
        return somar_meses(inicio, int(meses)) - timedelta(days=1)
    return inicio + timedelta(days=round(float(meses) * 30.4375) - 1)


def segunda_da_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


class Calendario:
    """Dias úteis a partir da data de início.

    - índice de dia útil: 0 = primeiro dia útil a partir do início;
    - dia corrido (offset): dias desde a data de início (o próprio início = 0);
    - semana: segunda a domingo; índice 0 = semana do início.
    """

    def __init__(
        self,
        inicio: Any,
        dias_semana: int = 5,
        horas_semana: float = 44.0,
        mudancas_jornada: Iterable[Mapping[str, Any]] = (),
        feriados_locais: Iterable[Any] = (),
        dias: int = 365 * 6,
    ):
        self.inicio = para_data(inicio)
        self.dias_semana = int(dias_semana)
        self.horas_semana_base = float(horas_semana)
        self.mudancas = sorted(
            ((para_data(m["a_partir_de"]), float(m["horas_semana"])) for m in mudancas_jornada),
            key=lambda x: x[0],
        )
        self.locais: dict[date, str] = {}
        for f in feriados_locais:
            if isinstance(f, Mapping):
                self.locais[para_data(f["data"])] = f.get("nome") or "Feriado local"
            else:
                self.locais[para_data(f)] = "Feriado local"
        self.feriados: dict[date, str] = {}
        fim = self.inicio + timedelta(days=dias)
        for ano in range(self.inicio.year, fim.year + 1):
            self.feriados.update(feriados_nacionais(ano))
        self.feriados.update(self.locais)
        self.semana0 = segunda_da_semana(self.inicio)
        self.uteis: list[date] = []
        self.offset: list[int] = []  # dia corrido de cada dia útil
        d = self.inicio
        while d < fim:
            if self.eh_util(d):
                self.uteis.append(d)
                self.offset.append((d - self.inicio).days)
            d += timedelta(days=1)

    # ------------------------------------------------------------------ dias

    def eh_util(self, d: date) -> bool:
        if d.weekday() >= self.dias_semana:  # 5 dias: seg a sex; 6: com sábado
            return False
        return d not in self.feriados

    def data(self, indice: int) -> date:
        return self.uteis[indice]

    def offset_de(self, d: date) -> int:
        return (d - self.inicio).days

    def data_do_offset(self, offset: int) -> date:
        return self.inicio + timedelta(days=offset)

    def indice_util(self, offset: int) -> int:
        """Primeiro dia útil no dia corrido `offset` ou depois."""
        return bisect.bisect_left(self.offset, offset)

    def ultimo_util_ate(self, offset: int) -> int:
        """Último dia útil no dia corrido `offset` ou antes (−1 se nenhum)."""
        return bisect.bisect_right(self.offset, offset) - 1

    # ------------------------------------------------------------------ semanas e jornada

    def semana(self, indice: int) -> int:
        return (self.uteis[indice] - self.semana0).days // 7

    def segunda(self, semana: int) -> date:
        return self.semana0 + timedelta(days=7 * semana)

    def horas_semana(self, semana: int) -> float:
        """Jornada da semana (vale a mudança que começa até o domingo dela)."""
        domingo = self.segunda(semana) + timedelta(days=6)
        horas = self.horas_semana_base
        for d, h in self.mudancas:
            if d <= domingo:
                horas = h
        return horas

    def horas_dia(self, indice: int) -> float:
        return self.horas_semana(self.semana(indice)) / self.dias_semana

    def jornadas(self) -> list[float]:
        """Horas por dia distintas que aparecem no calendário."""
        return sorted({self.horas_semana_base / self.dias_semana} | {h / self.dias_semana for _, h in self.mudancas})

    def dias_uteis_ate(self, d: date) -> int:
        """Quantidade de dias úteis do início até `d` (inclusive)."""
        return self.ultimo_util_ate(self.offset_de(d)) + 1

    def feriados_no_periodo(self, ate: date) -> list[dict[str, Any]]:
        return [{"data": d.isoformat(), "nome": n, "local": d in self.locais}
                for d, n in sorted(self.feriados.items()) if self.inicio <= d <= ate]
