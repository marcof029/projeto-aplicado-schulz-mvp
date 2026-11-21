"""
07_testes.py - Testes automatizados do MVP (Entrega 03). Execução: python -m unittest 07_testes.py -v
"""
import importlib
import tempfile
import unittest
from pathlib import Path

cl = importlib.import_module("04_classes")


def nova_medicao(**kw):
    base = dict(id_equipamento=1, id_tecnico=1, setor_solicitante="Usinagem I", codigo_mmc="500011",
                parametro_medido="62P_DIAMETRO_2", valor_nominal=6.075, tolerancia_min=-0.01,
                tolerancia_max=0.01, medida_1=6.0781314, medida_2=6.0780314)
    base.update(kw)
    return cl.Medicao(**base)


class TestMedicao(unittest.TestCase):
    def test_media_erro_e_desvio_do_exemplo_real(self):
        m = nova_medicao()
        self.assertAlmostEqual(m.valor_obtido, 6.0780814, places=9)
        self.assertAlmostEqual(m.erro, 0.0030814, places=9)
        self.assertAlmostEqual(m.desvio, 0.0030814, places=9)
        self.assertEqual(m.status_resultado, cl.STATUS_APROVADO)

    def test_erro_em_modulo_e_desvio_com_sinal(self):
        m = nova_medicao(medida_1=6.060, medida_2=6.060)
        self.assertAlmostEqual(m.desvio, -0.015, places=9)
        self.assertAlmostEqual(m.erro, 0.015, places=9)

    def test_faixa_aceitavel(self):
        inf, sup = nova_medicao().faixa
        self.assertAlmostEqual(inf, 6.065, places=9)
        self.assertAlmostEqual(sup, 6.085, places=9)

    def test_reprovado_acima_e_abaixo(self):
        self.assertEqual(nova_medicao(medida_1=6.0951, medida_2=6.0953).status_resultado, cl.STATUS_REPROVADO)
        self.assertEqual(nova_medicao(medida_1=6.0649, medida_2=6.0649).status_resultado, cl.STATUS_REPROVADO)

    def test_limites_sao_inclusivos(self):
        self.assertTrue(nova_medicao(medida_1=6.085, medida_2=6.085).esta_aprovada())
        self.assertTrue(nova_medicao(medida_1=6.065, medida_2=6.065).esta_aprovada())

    def test_tolerancia_assimetrica(self):  # PLANICIDADE_REF: Tol- = 0 e Tol+ = 0,05
        base = dict(valor_nominal=0.0, tolerancia_min=0.0, tolerancia_max=0.05)
        self.assertEqual(nova_medicao(medida_1=0.002167, medida_2=0.002267, **base).status_resultado, cl.STATUS_APROVADO)
        self.assertEqual(nova_medicao(medida_1=-0.001, medida_2=-0.001, **base).status_resultado, cl.STATUS_REPROVADO)

    def test_equivalencia_desvio_e_limites_absolutos(self):
        """Coerência matemática: |x - nominal| dentro de [Tol-, Tol+] equivale a x dentro de [nominal+Tol-, nominal+Tol+]."""
        for obtido in (6.060, 6.065, 6.0701, 6.075, 6.085, 6.0851, 6.1):
            m = nova_medicao(medida_1=obtido, medida_2=obtido)
            por_desvio = m.tolerancia_min - cl.EPSILON <= m.desvio <= m.tolerancia_max + cl.EPSILON
            self.assertEqual(m.esta_aprovada(), por_desvio, obtido)

    def test_imutabilidade(self):
        m = nova_medicao()
        for campo in ("medida_1", "medida_2", "valor_nominal", "tolerancia_min", "status_resultado",
                      "valor_obtido", "erro", "id_medicao", "data_medicao"):
            with self.subTest(campo=campo), self.assertRaises(AttributeError):
                setattr(m, campo, 1)

    def test_registrar_persistencia_so_uma_vez(self):
        m = nova_medicao()
        m.registrar_persistencia(1, "2026-08-13 16:16:26")
        with self.assertRaises(cl.ErroValidacao):
            m.registrar_persistencia(2, "2026-08-14 10:00:00")

    def test_mmc_normalizada_e_virgula_decimal(self):
        self.assertEqual(nova_medicao(codigo_mmc="500.011").codigo_mmc, "500011")
        self.assertAlmostEqual(nova_medicao(valor_nominal="6,075").valor_nominal, 6.075)

    def test_validacoes(self):
        for kw in (dict(tolerancia_min=0.1, tolerancia_max=-0.1), dict(medida_1="abc"), dict(medida_1=float("nan")),
                   dict(medida_2=True), dict(codigo_mmc="ABC"), dict(setor_solicitante="  "), dict(id_equipamento=0),
                   dict(data_medicao="13/08/2026")):
            with self.subTest(kw=kw), self.assertRaises(cl.ErroValidacao):
                nova_medicao(**kw)


class TestDominio(unittest.TestCase):
    def test_placeholders_viram_none(self):
        e = cl.Equipamento("703.1208", "Dispositivo de controle", "Não consta", "---")
        self.assertIsNone(e.fabricante)
        self.assertIsNone(e.modelo)

    def test_tag_padronizada(self):
        self.assertEqual(cl.Equipamento(" paq-2026-01 ", "Paquímetro").codigo_tag, "PAQ-2026-01")

    def test_texto_normalizado(self):
        self.assertEqual(cl.Tecnico("  Jose   Alcides\tRosa  Junior ", "Metrologia").nome_tecnico, "Jose Alcides Rosa Junior")

    def test_campos_obrigatorios(self):
        with self.assertRaises(cl.ErroValidacao):
            cl.Equipamento("", "X")

    def test_id_definido_uma_unica_vez(self):
        t = cl.Tecnico("Ana", "Metrologia")
        t.id_tecnico = 1
        with self.assertRaises(cl.ErroValidacao):
            t.id_tecnico = 2


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self.con = cl.ConexaoSQLite(":memory:").conectar()
        self.con.criar_esquema()
        self.log = cl.LogAtualizacoes()
        self.tec = cl.TecnicoDAO(self.con, self.log)
        self.eq = cl.EquipamentoDAO(self.con, self.log)
        self.med = cl.MedicaoDAO(self.con, self.log)
        self.t = self.tec.inserir(cl.Tecnico("Jose Alcides Rosa Junior", "Metrologia"))
        self.e = self.eq.inserir(cl.Equipamento("703.1208", "Dispositivo de controle"))

    def tearDown(self):
        self.con.fechar()

    def _med(self, **kw):
        return nova_medicao(id_equipamento=self.e.id_equipamento, id_tecnico=self.t.id_tecnico, **kw)

    def test_chaves_estrangeiras_ativas(self):
        self.assertEqual(self.con.consultar("PRAGMA foreign_keys")[0][0], 1)

    def test_inserir_e_ler_medicao(self):
        m = self.med.inserir(self._med())
        self.assertIsNotNone(m.id_medicao)
        self.assertIsNotNone(m.data_medicao)  # DEFAULT do banco lido de volta
        lido = self.med.buscar_por_id(m.id_medicao)
        self.assertAlmostEqual(lido.valor_obtido, m.valor_obtido, places=9)
        self.assertEqual(lido.status_resultado, m.status_resultado)

    def test_medicao_dao_sem_atualizar_nem_excluir(self):
        self.assertFalse(hasattr(self.med, "atualizar"))
        self.assertFalse(hasattr(self.med, "excluir"))

    def test_banco_rejeita_update_incoerente_na_medicao(self):
        m = self.med.inserir(self._med())
        with self.assertRaises(cl.ErroIntegridade):  # CHECK protege os valores derivados
            self.con.executar("UPDATE medicao SET status_resultado = 'REPROVADO' WHERE id_medicao = ?", (m.id_medicao,))

    def test_update_tecnico_gera_log(self):
        self.assertTrue(self.tec.atualizar_setor(self.t.id_tecnico, "Qualidade"))
        self.assertEqual(self.tec.buscar_por_id(self.t.id_tecnico).setor, "Qualidade")
        registro = self.log.registros[-1]
        self.assertEqual((registro["entidade"], registro["campo"], registro["antes"], registro["depois"]),
                         ("tecnico", "setor", "Metrologia", "Qualidade"))

    def test_update_equipamento_registra_cada_campo_alterado(self):
        e = self.eq.buscar_por_id(self.e.id_equipamento)
        e.nome_equipamento, e.fabricante = "Novo nome", "Schulz"
        self.eq.atualizar(e)
        self.assertEqual({r["campo"] for r in self.log.registros}, {"nome_equipamento", "fabricante"})

    def test_update_sem_mudanca_nao_gera_log(self):
        self.tec.atualizar(self.tec.buscar_por_id(self.t.id_tecnico))
        self.assertEqual(self.log.registros, [])

    def test_log_em_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "log.txt"
            log = cl.LogAtualizacoes(caminho)
            cl.TecnicoDAO(self.con, log).atualizar_setor(self.t.id_tecnico, "Qualidade")
            self.assertIn("setor: 'Metrologia' -> 'Qualidade'", caminho.read_text(encoding="utf-8"))

    def test_update_inexistente(self):
        self.assertFalse(self.tec.atualizar_setor(999, "X"))
        with self.assertRaises(cl.RegistroNaoEncontrado):
            self.tec.atualizar(cl.Tecnico("Fantasma", "X", id_tecnico=999))

    def test_fk_inexistente(self):
        with self.assertRaises(cl.ErroIntegridade):
            self.med.inserir(nova_medicao(id_equipamento=99, id_tecnico=self.t.id_tecnico))

    def test_tag_duplicada_mesmo_com_espaco_e_minuscula(self):
        with self.assertRaises(cl.ErroIntegridade):
            self.eq.inserir(cl.Equipamento("703.1208 ", "Outro"))

    def test_buscar_tag_padronizada(self):
        self.eq.inserir(cl.Equipamento("PAQ-2026-01", "Paquímetro"))
        self.assertIsNotNone(self.eq.buscar_por_tag(" paq-2026-01 "))

    def test_excluir_tecnico_com_medicao_e_bloqueado(self):
        self.med.inserir(self._med())
        with self.assertRaises(cl.ErroIntegridade):
            self.tec.excluir(self.t.id_tecnico)

    def test_rollback_da_transacao(self):
        with self.assertRaises(cl.ErroIntegridade), self.con.transacao():
            self.med.inserir(self._med())
            self.med.inserir(nova_medicao(id_equipamento=99, id_tecnico=self.t.id_tecnico))
        self.assertEqual(len(self.med.listar()), 0)

    def test_join_resumo_e_parecer(self):
        self.med.inserir(self._med())
        self.med.inserir(self._med(medida_1=6.2, medida_2=6.2, parametro_medido="X"))
        self.eq.inserir(cl.Equipamento("SEM-MEDICAO", "Sem medições"))
        rel = self.med.relatorio_calibracao("703.1208")
        self.assertEqual([r["status_resultado"] for r in rel], ["APROVADO", "REPROVADO"])
        self.assertAlmostEqual(rel[0]["limite_min"], 6.065, places=9)
        resumo = {r["codigo_tag"]: (r["total"], r["aprovadas"], r["reprovadas"]) for r in self.med.resumo_por_equipamento()}
        self.assertEqual(resumo["703.1208"], (2, 1, 1))
        self.assertEqual(resumo["SEM-MEDICAO"], (0, 0, 0))
        self.assertEqual(self.med.parecer_instrumento("703.1208"), cl.STATUS_REPROVADO)
        self.assertIsNone(self.med.parecer_instrumento("SEM-MEDICAO"))
        self.assertEqual(len(self.med.listar_reprovadas()), 1)

    def test_parecer_aprovado_quando_todas_aprovadas(self):
        self.med.inserir(self._med())
        self.assertEqual(self.med.parecer_instrumento("703.1208"), cl.STATUS_APROVADO)

    def test_injecao_sql_tratada_como_dado(self):
        self.assertIsNone(self.eq.buscar_por_tag("' OR '1'='1"))
        self.assertEqual(len(self.tec.listar()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
