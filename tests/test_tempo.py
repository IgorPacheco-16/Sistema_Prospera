from datetime import date, datetime

import tempo


def test_hoje_brasilia_retorna_data_no_fuso_de_sao_paulo(monkeypatch):
    chamadas = []

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            chamadas.append(tz)
            return datetime(2026, 5, 21, 0, 30, tzinfo=tz)

    monkeypatch.setattr(tempo, "datetime", FakeDateTime)

    assert tempo.hoje_brasilia() == date(2026, 5, 21)
    assert chamadas == [tempo.BRASILIA_TZ]
