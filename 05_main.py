"""
05_main.py - Projeto Aplicado I - Schulz S.A. - Entrega 03 (MVP - Parte 1)

Script de demonstração: cria o banco SQLite, instancia os objetos do domínio, insere registros de teste,
executa consultas relacionais (JOIN), demonstra UPDATE com log de atualizações, a imutabilidade da
medição e o tratamento de erros, e exibe o relatório de calibração no terminal.

Uso:  python 05_main.py [caminho_do_banco]   (padrão: schulz_calibracao.db, recriado a cada execução)
"""
import importlib
import sys
from pathlib import Path

# O arquivo do roteiro se chama 04_classes.py (nome iniciado por dígito); por isso o import dinâmico.
cl = importlib.import_module("04_classes")

NOME_LOG = "schulz_atualizacoes.log"


def titulo(texto: str) -> None:
    print(f"\n{'=' * 100}\n{texto}\n{'=' * 100}")


def imprimir_relatorio(linhas) -> None:
    """Relatório de calibração. Valores guardados com 7 casas e exibidos com 3 (regra ETL-16)."""
    cab = (f"{'ID':>3} {'TAG':<9} {'Parâmetro':<30} {'Técnico':<25} {'Faixa aceitável':<19} "
           f"{'Obtido':>8} {'Desvio':>8} {'Erro':>6}  {'Status':<9}")
    print(cab)
    print("-" * len(cab))
    for l in linhas:
        faixa = f"[{l['limite_min']:.3f} ; {l['limite_max']:.3f}]"
        print(f"{l['id_medicao']:>3} {l['codigo_tag']:<9} {l['parametro_medido']:<30} {l['nome_tecnico']:<25} "
              f"{faixa:<19} {l['valor_obtido']:>8.3f} {l['desvio']:>+8.3f} {l['erro']:>6.3f}  {l['status_resultado']:<9}")


def capturar(descricao: str, acao) -> None:
    """Executa uma ação que deve falhar e mostra a exceção capturada (demonstra o tratamento de erros)."""
    try:
        acao()
        print(f"  [FALHA] {descricao}: a operação foi aceita, mas deveria ser recusada.")
    except (cl.ErroSistema, AttributeError) as e:
        print(f"  [OK] {descricao}\n       -> {type(e).__name__}: {e}")


def main(caminho_banco: str) -> int:
    arquivo = Path(caminho_banco)
    if arquivo.exists():
        arquivo.unlink()  # recria o banco de demonstração
    log = cl.LogAtualizacoes(NOME_LOG, reiniciar=True)

    with cl.ConexaoSQLite(arquivo) as con:
        titulo("1. Criação do banco (03_banco.sql) e conexão")
        con.criar_esquema()
        fk = con.consultar("PRAGMA foreign_keys")[0][0]
        tabelas = [r["name"] for r in con.consultar(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        print(f"Banco: {arquivo} | Tabelas: {', '.join(tabelas)} | PRAGMA foreign_keys = {fk}")

        tec_dao, equip_dao, med_dao = cl.TecnicoDAO(con, log), cl.EquipamentoDAO(con, log), cl.MedicaoDAO(con, log)

        titulo("2. Instanciação dos objetos e inserção de registros de teste (INSERT)")
        jose = tec_dao.inserir(cl.Tecnico("Jose Alcides Rosa Junior", "Metrologia"))
        cleocir = tec_dao.inserir(cl.Tecnico("Cleocir de Souza", "Metrologia"))
        disp = equip_dao.inserir(cl.Equipamento("703.1208", "Dispositivo de controle", "Não consta", "Não consta"))
        teste = equip_dao.inserir(cl.Equipamento(" teste-001 ", "Calibrador fictício de teste", "Fabricante Fictício", "FF-01"))
        print(f"{jose}\n{cleocir}\n{disp}  (fabricante={disp.fabricante}, modelo={disp.modelo}; 'Não consta' virou None)")
        print(f"{teste}  (TAG ' teste-001 ' padronizada para {teste.codigo_tag!r})")

        # As duas primeiras medições usam valores reais das planilhas da Schulz (Entrega 01); as demais são
        # SIMULADAS, criadas só para testar APROVADO/REPROVADO e o limite da tolerância.
        medicoes = [
            cl.Medicao(disp.id_equipamento, jose.id_tecnico, "Usinagem I", "500.011", "62P_DIAMETRO_2",
                       6.075, -0.01, 0.01, 6.0781314, 6.0780314, "2026-08-13 16:16:26"),
            cl.Medicao(disp.id_equipamento, jose.id_tecnico, "Usinagem I", "500011", "PLANICIDADE_REF",
                       0.0, 0.0, 0.05, 0.002167, 0.002267, "2026-08-13 16:16:26"),
            cl.Medicao(disp.id_equipamento, cleocir.id_tecnico, "Usinagem I", "500011", "62P_DIAMETRO_SIMULADO",
                       6.075, -0.01, 0.01, 6.0951, 6.0953, "2026-08-14 09:30:00"),
            cl.Medicao(teste.id_equipamento, cleocir.id_tecnico, "Pintura", "500011", "LIMITE_SUPERIOR_SIMULADO",
                       6.075, -0.01, 0.01, 6.085, 6.085, "2026-08-14 10:00:00"),
            cl.Medicao(teste.id_equipamento, jose.id_tecnico, "Pintura", "500011", "ABAIXO_DO_LIMITE_SIMULADO",
                       6.075, -0.01, 0.01, 6.060, 6.060, "2026-08-14 10:05:00"),
        ]
        for m in medicoes:
            med_dao.inserir(m)
            print(f"id={m.id_medicao}  {m}")

        titulo("3. Relatório de calibração do instrumento 703.1208 (SELECT com JOIN: medicao + equipamento + tecnico)")
        imprimir_relatorio(med_dao.relatorio_calibracao("703.1208"))
        print(f"\nParecer final do instrumento 703.1208: {med_dao.parecer_instrumento('703.1208')}"
              "  (APROVADO só se todas as medições forem aprovadas)")

        titulo("4. Resumo e parecer por equipamento (LEFT JOIN + GROUP BY)")
        print(f"{'TAG':<10} {'Equipamento':<32} {'Total':>5} {'Aprov.':>6} {'Reprov.':>7}  Parecer")
        for r in med_dao.resumo_por_equipamento():
            print(f"{r['codigo_tag']:<10} {r['nome_equipamento']:<32} {r['total']:>5} {r['aprovadas']:>6} "
                  f"{r['reprovadas']:>7}  {med_dao.parecer_instrumento(r['codigo_tag'])}")

        titulo("5. Consulta parametrizada: TAG digitada em minúsculas e tentativa de SQL Injection")
        print(f"Busca por ' 703.1208 ': {equip_dao.buscar_por_tag(' 703.1208 ')}")
        print(f"Busca por ' teste-001': {equip_dao.buscar_por_tag(' teste-001')}  (padronizada com strip + maiúsculas)")
        malicioso = "' OR '1'='1"
        print(f"Busca com texto malicioso {malicioso!r}: {equip_dao.buscar_por_tag(malicioso)} "
              "(parâmetro tratado como dado, não como SQL)")

        titulo("6. Atualização (UPDATE) com log: cada campo alterado é registrado (antes -> depois)")
        print(f"UPDATE do setor do técnico: {tec_dao.atualizar_setor(jose.id_tecnico, 'Qualidade')} | "
              f"agora: {tec_dao.buscar_por_id(jose.id_tecnico)}")
        equip = equip_dao.buscar_por_id(disp.id_equipamento)
        equip.nome_equipamento, equip.fabricante = "Dispositivo de controle dimensional", "Schulz"
        equip_dao.atualizar(equip)
        print(f"UPDATE do equipamento: {equip_dao.buscar_por_id(disp.id_equipamento)} (fabricante={equip.fabricante})")
        tec_dao.atualizar_setor(jose.id_tecnico, "Metrologia")  # reverte o setor (também registrado)
        print(f"\nLog de atualizações ({NOME_LOG}):")
        for linha in log.linhas():
            print(f"  {linha}")

        titulo("7. Imutabilidade da medição (rastreabilidade): um ensaio registrado não pode ser alterado")
        original = medicoes[2]
        capturar("Alterar medida_1 de uma medição registrada", lambda: setattr(original, "medida_1", 6.0751))
        capturar("Digitar o status_resultado (é calculado, não atribuído)", lambda: setattr(original, "status_resultado", "APROVADO"))
        capturar("Registrar de novo uma medição já gravada", lambda: original.registrar_persistencia(99, "2026-01-01 00:00:00"))
        print(f"  Medição {original.id_medicao} permanece: {original.status_resultado}. "
              "Para corrigir um ensaio, registra-se um novo ensaio; o original fica no histórico.")

        titulo("8. Tratamento de erros (cada operação abaixo deve ser recusada)")
        capturar("Medição para equipamento inexistente (violação de FK)",
                 lambda: med_dao.inserir(cl.Medicao(999, jose.id_tecnico, "Usinagem I", "500011", "X", 1, -0.1, 0.1, 1, 1)))
        capturar("Mesma TAG digitada com espaço e minúsculas (padronização + UNIQUE)",
                 lambda: equip_dao.inserir(cl.Equipamento("703.1208 ", "Outro dispositivo")))
        capturar("Tolerâncias invertidas (validação de domínio, antes do banco)",
                 lambda: cl.Medicao(1, 1, "Usinagem I", "500011", "X", 1, 0.1, -0.1, 1, 1))
        capturar("Valor medido não numérico (validação de domínio)",
                 lambda: cl.Medicao(1, 1, "Usinagem I", "500011", "X", 1, -0.1, 0.1, "abc", 1))
        capturar("Nome de técnico vazio (validação de domínio)", lambda: cl.Tecnico("   ", "Metrologia"))
        capturar("Excluir técnico que possui medições (ON DELETE RESTRICT)", lambda: tec_dao.excluir(jose.id_tecnico))
        capturar("Atualizar técnico inexistente", lambda: tec_dao.atualizar(cl.Tecnico("Fantasma", "X", id_tecnico=999)))
        print(f"  [OK] atualizar_setor de técnico inexistente devolve: {tec_dao.atualizar_setor(999, 'X')}")

        titulo("9. Transação atômica: se a segunda inserção falhar, a primeira é desfeita (ROLLBACK)")
        antes = len(med_dao.listar())
        try:
            with con.transacao():
                med_dao.inserir(cl.Medicao(disp.id_equipamento, jose.id_tecnico, "Usinagem I", "500011", "TRANSACAO_1", 1, -0.1, 0.1, 1, 1))
                med_dao.inserir(cl.Medicao(999, jose.id_tecnico, "Usinagem I", "500011", "TRANSACAO_2", 1, -0.1, 0.1, 1, 1))
        except cl.ErroIntegridade as e:
            print(f"  Falha capturada: {e}")
        print(f"  Medições antes: {antes} | depois: {len(med_dao.listar())} (a primeira inserção foi desfeita)")

        titulo("10. Medições reprovadas (todos os equipamentos) e relatório geral")
        imprimir_relatorio(med_dao.listar_reprovadas())
        print()
        imprimir_relatorio(med_dao.relatorio_calibracao())
    print("\nExecução concluída sem erros inesperados.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "schulz_calibracao.db"))
