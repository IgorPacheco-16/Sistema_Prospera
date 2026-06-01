from datetime import datetime, time


STATUS_EM_ANDAMENTO = "EM ANDAMENTO"
STATUS_EM_VALIDACAO = "EM VALIDA\u00c7\u00c3O"
STATUS_ENTREGUE = "ENTREGUE"


def resumo_metricas_responsavel():
    return {
        "total_atribuidas": 0,
        "pendentes": 0,
        "em_andamento": 0,
        "entregues": 0,
        "concluidas": 0,
        "atrasadas": 0,
        "recusadas": 0,
        "abertas": 0,
        "taxa_atraso": 0.0,
        "taxa_recusa": 0.0,
        "taxa_aprovacao": None,
        "media_para_iniciar": None,
        "media_em_execucao": None,
        "media_conclusao": None,
        "maior_tempo_parada": None,
    }


def nome_usuario_metricas(usuario):
    return (getattr(usuario, "nome", None) or getattr(usuario, "email", None) or "").strip()


def nome_setor_usuario(usuario):
    setor = getattr(usuario, "setor", None)
    return (getattr(setor, "nome", None) or "-").strip()


def nome_setor_tarefa(tarefa):
    setor = getattr(tarefa, "setor", None)
    return (getattr(setor, "nome", None) or "-").strip()


def fim_conclusao_tarefa(tarefa):
    return getattr(tarefa, "concluida_em", None) or getattr(tarefa, "validada_em", None)


def fim_execucao_tarefa(tarefa):
    return (
        getattr(tarefa, "enviada_validacao_em", None)
        or getattr(tarefa, "entregue_em", None)
        or getattr(tarefa, "concluida_em", None)
        or getattr(tarefa, "validada_em", None)
    )


def tarefa_concluida_metricas(tarefa):
    return bool(
        fim_conclusao_tarefa(tarefa)
        or getattr(tarefa, "validado", False)
    )


def tarefa_entregue_metricas(tarefa):
    return bool(
        not tarefa_concluida_metricas(tarefa)
        and (
            getattr(tarefa, "entregue", False)
            or getattr(tarefa, "status", None) in [STATUS_EM_VALIDACAO, STATUS_ENTREGUE]
            or getattr(tarefa, "enviada_validacao_em", None)
        )
    )


def tarefa_em_andamento_metricas(tarefa):
    return bool(
        not tarefa_concluida_metricas(tarefa)
        and not tarefa_entregue_metricas(tarefa)
        and (
            getattr(tarefa, "status", None) == STATUS_EM_ANDAMENTO
            or getattr(tarefa, "iniciada_em", None)
        )
    )


def tarefa_aberta_metricas(tarefa):
    return not tarefa_concluida_metricas(tarefa)


def tarefa_atrasada_metricas(tarefa, hoje):
    prazo = getattr(tarefa, "prazo", None)
    return bool(prazo and prazo < hoje and tarefa_aberta_metricas(tarefa))


def tarefa_recusada_metricas(tarefa):
    return bool(getattr(tarefa, "recusada_em", None) or getattr(tarefa, "motivo_recusa", None))


def diferenca_dias(inicio, fim):
    if not inicio or not fim or fim < inicio:
        return None
    return (fim - inicio).total_seconds() / 86400


def media(valores):
    validos = [valor for valor in valores if valor is not None]
    if not validos:
        return None
    return sum(validos) / len(validos)


def percentual(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


def data_hora_final_do_dia(data):
    return datetime.combine(data, time.max)


def tempos_tarefa(tarefa, agora):
    criada_em = getattr(tarefa, "criada_em", None)
    iniciada_em = getattr(tarefa, "iniciada_em", None)
    fim_execucao = fim_execucao_tarefa(tarefa)
    fim_conclusao = fim_conclusao_tarefa(tarefa)

    return {
        "para_iniciar": diferenca_dias(criada_em, iniciada_em),
        "em_execucao": diferenca_dias(iniciada_em, fim_execucao),
        "conclusao": diferenca_dias(criada_em, fim_conclusao),
        "parada": diferenca_dias(criada_em, agora) if criada_em and tarefa_aberta_metricas(tarefa) else None,
    }


def atualizar_resumo_metricas(resumo, tarefa, hoje, agora=None):
    resumo["total_atribuidas"] += 1

    if tarefa_concluida_metricas(tarefa):
        resumo["concluidas"] += 1
    elif tarefa_entregue_metricas(tarefa):
        resumo["entregues"] += 1
        resumo["abertas"] += 1
    elif tarefa_em_andamento_metricas(tarefa):
        resumo["em_andamento"] += 1
        resumo["abertas"] += 1
    else:
        resumo["pendentes"] += 1
        resumo["abertas"] += 1

    if tarefa_atrasada_metricas(tarefa, hoje):
        resumo["atrasadas"] += 1
    if tarefa_recusada_metricas(tarefa):
        resumo["recusadas"] += 1

    if agora:
        tempos = tempos_tarefa(tarefa, agora)
        resumo.setdefault("_tempos_para_iniciar", []).append(tempos["para_iniciar"])
        resumo.setdefault("_tempos_em_execucao", []).append(tempos["em_execucao"])
        resumo.setdefault("_tempos_conclusao", []).append(tempos["conclusao"])
        if tempos["parada"] is not None:
            atual = resumo["maior_tempo_parada"]
            resumo["maior_tempo_parada"] = max(tempos["parada"], atual or 0)


def finalizar_resumo(resumo):
    total = resumo["total_atribuidas"]
    resumo["entregues_total"] = resumo["entregues"] + resumo["concluidas"]
    resumo["taxa_atraso"] = percentual(resumo["atrasadas"], total)
    resumo["taxa_recusa"] = percentual(resumo["recusadas"], total)

    base_aprovacao = resumo["concluidas"] + resumo["recusadas"]
    if base_aprovacao:
        resumo["taxa_aprovacao"] = percentual(resumo["concluidas"], base_aprovacao)

    resumo["media_para_iniciar"] = media(resumo.pop("_tempos_para_iniciar", []))
    resumo["media_em_execucao"] = media(resumo.pop("_tempos_em_execucao", []))
    resumo["media_conclusao"] = media(resumo.pop("_tempos_conclusao", []))
    return resumo


def resumo_tem_valores(resumo):
    return any(
        resumo[chave]
        for chave in [
            "total_atribuidas",
            "pendentes",
            "em_andamento",
            "entregues",
            "concluidas",
            "atrasadas",
            "recusadas",
        ]
    )


def nova_linha_usuario(usuario):
    resumo = resumo_metricas_responsavel()
    resumo["usuario"] = usuario
    resumo["nome"] = nome_usuario_metricas(usuario)
    resumo["setor"] = nome_setor_usuario(usuario)
    return resumo


def metricas_usuario(tarefas, usuario, hoje):
    agora = data_hora_final_do_dia(hoje)
    resumo = nova_linha_usuario(usuario)
    usuario_id = getattr(usuario, "id", None)

    for tarefa in tarefas:
        responsaveis = list(getattr(tarefa, "responsaveis", []) or [])
        if any(getattr(responsavel, "id", None) == usuario_id for responsavel in responsaveis):
            atualizar_resumo_metricas(resumo, tarefa, hoje, agora)

    return finalizar_resumo(resumo)


def ordenar_por_entregas(linhas):
    return sorted(linhas, key=lambda linha: (-linha["entregues_total"], linha["nome"].lower()))


def top_com_valor(linhas, chave, reverso=True):
    filtradas = [linha for linha in linhas if linha.get(chave)]
    fator = -1 if reverso else 1
    return sorted(filtradas, key=lambda linha: (fator * linha[chave], linha["nome"].lower()))


def tarefa_resumo(tarefa, hoje, agora, responsavel=None):
    tempos = tempos_tarefa(tarefa, agora)
    return {
        "tarefa": tarefa,
        "responsavel": responsavel,
        "responsavel_nome": nome_usuario_metricas(responsavel) if responsavel else "Geral do setor",
        "nome": getattr(tarefa, "nome", ""),
        "op": getattr(getattr(tarefa, "op", None), "nome", "-"),
        "setor": nome_setor_tarefa(tarefa),
        "status": getattr(tarefa, "status", "-"),
        "prazo": getattr(tarefa, "prazo", None),
        "atrasada": tarefa_atrasada_metricas(tarefa, hoje),
        "dias_parada": tempos["parada"],
    }


def setores_sobrecarregados(tarefas, hoje):
    linhas = {}
    for tarefa in tarefas:
        if not tarefa_aberta_metricas(tarefa):
            continue

        setor_id = getattr(tarefa, "setor_id", None)
        if setor_id not in linhas:
            linhas[setor_id] = {
                "setor": nome_setor_tarefa(tarefa),
                "abertas": 0,
                "atrasadas": 0,
                "sem_responsavel": 0,
            }

        linhas[setor_id]["abertas"] += 1
        if tarefa_atrasada_metricas(tarefa, hoje):
            linhas[setor_id]["atrasadas"] += 1
        if not list(getattr(tarefa, "responsaveis", []) or []):
            linhas[setor_id]["sem_responsavel"] += 1

    return sorted(
        linhas.values(),
        key=lambda linha: (-linha["abertas"], -linha["atrasadas"], linha["setor"].lower()),
    )


def ranking_metricas_responsaveis(tarefas, hoje):
    agora = data_hora_final_do_dia(hoje)
    linhas_por_usuario = {}
    geral_setor = resumo_metricas_responsavel()
    geral_setor["nome"] = "Geral do setor"
    geral_setor["setor"] = "-"

    tarefas_sem_responsavel = []
    tarefas_paradas = []

    for tarefa in tarefas:
        responsaveis = list(getattr(tarefa, "responsaveis", []) or [])
        if not responsaveis:
            atualizar_resumo_metricas(geral_setor, tarefa, hoje, agora)
            tarefas_sem_responsavel.append(tarefa_resumo(tarefa, hoje, agora))
            continue

        for responsavel in responsaveis:
            chave = getattr(responsavel, "id", None)
            if chave not in linhas_por_usuario:
                linhas_por_usuario[chave] = nova_linha_usuario(responsavel)

            atualizar_resumo_metricas(linhas_por_usuario[chave], tarefa, hoje, agora)
            if tarefa_aberta_metricas(tarefa):
                tarefas_paradas.append(tarefa_resumo(tarefa, hoje, agora, responsavel))

    ranking = [
        finalizar_resumo(linha)
        for linha in linhas_por_usuario.values()
        if resumo_tem_valores(linha)
    ]
    ranking = ordenar_por_entregas(ranking)
    geral_setor = finalizar_resumo(geral_setor)

    totais = resumo_metricas_responsavel()
    for linha in ranking:
        for chave in [
            "total_atribuidas",
            "pendentes",
            "em_andamento",
            "entregues",
            "concluidas",
            "atrasadas",
            "recusadas",
            "abertas",
        ]:
            totais[chave] += linha[chave]
    totais["sem_responsavel"] = len(tarefas_sem_responsavel)
    finalizar_resumo(totais)

    tarefas_paradas.sort(
        key=lambda linha: (-(linha["dias_parada"] or 0), linha["responsavel_nome"].lower(), linha["nome"].lower())
    )
    tarefas_sem_responsavel.sort(
        key=lambda linha: (linha["setor"].lower(), linha["op"].lower(), linha["nome"].lower())
    )

    # O modelo atual guarda apenas o estado/campo de recusa atual.
    # Ranking de retrabalho real precisa de historico de recusas por tarefa no futuro.
    tarefas_com_retrabalho = []

    return {
        "usuarios": ranking,
        "geral_setor": geral_setor if resumo_tem_valores(geral_setor) else None,
        "totais": totais,
        "velocidade": {
            "mais_rapidos": top_com_valor(ranking, "media_conclusao", reverso=False),
            "mais_lentos_para_iniciar": top_com_valor(ranking, "media_para_iniciar"),
            "mais_lentos_em_execucao": top_com_valor(ranking, "media_em_execucao"),
            "tarefas_paradas": tarefas_paradas,
        },
        "produtividade": {
            "mais_entregas": top_com_valor(ranking, "entregues_total"),
        },
        "qualidade": {
            "mais_recusadas": top_com_valor(ranking, "recusadas"),
            "maior_taxa_recusa": top_com_valor(ranking, "taxa_recusa"),
            "melhor_taxa_aprovacao": top_com_valor(
                [linha for linha in ranking if linha["taxa_aprovacao"] is not None],
                "taxa_aprovacao",
            ),
            "tarefas_com_retrabalho": tarefas_com_retrabalho,
            "nota_retrabalho": (
                "Tarefas com mais retrabalho dependem de historico de recusas por tarefa; "
                "hoje o model possui apenas recusada_em/motivo_recusa."
            ),
        },
        "carga": {
            "mais_abertas": top_com_valor(ranking, "abertas"),
            "mais_atrasadas": top_com_valor(ranking, "atrasadas"),
            "tarefas_sem_responsavel": tarefas_sem_responsavel,
            "setores_sobrecarregados": setores_sobrecarregados(tarefas, hoje),
        },
    }
