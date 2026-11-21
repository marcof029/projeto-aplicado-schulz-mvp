"""
04_classes.py - Projeto Aplicado I - Schulz S.A. - Entrega 03 (MVP - Parte 1)

Classes de domínio (Tecnico, Equipamento, Medicao) e camada de conexão e persistência
(ConexaoSQLite, TecnicoDAO, EquipamentoDAO, MedicaoDAO) sobre o banco SQLite modelado
na Entrega 02 (03_banco.sql).

Convenções:
  - Atributos "privados" (prefixo _) expostos por properties com validação (encapsulamento).
  - Valores derivados da Medicao (média, erro e status) são calculados, nunca informados.
  - Medicao é IMUTÁVEL (sem setters): um ensaio registrado não pode ser alterado (rastreabilidade, RN-08).
  - Todo UPDATE em Tecnico e Equipamento gera um registro no LogAtualizacoes (valor antes -> depois).
  - Todo acesso ao banco usa consultas parametrizadas (sem concatenar texto em SQL).
  - Erros do sqlite3 são traduzidos para exceções de domínio (ErroBancoDados e derivadas).
"""
from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

# ----------------------------------------------------------------------------------------
# Constantes de domínio
# ----------------------------------------------------------------------------------------
EPSILON = 1e-7  # margem numérica (mesma da Aula 02) usada na comparação com os limites de tolerância
STATUS_APROVADO = "APROVADO"
STATUS_REPROVADO = "REPROVADO"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
CAMINHO_DDL_PADRAO = Path(__file__).with_name("03_banco.sql")

# Valores que as planilhas usam no lugar de nulo (regra ETL-11 da Entrega 01)
_PLACEHOLDERS_NULOS = {"", "---", "-----", "não consta", "nao consta", "não se aplica", "nao se aplica"}


# ----------------------------------------------------------------------------------------
# Exceções
# ----------------------------------------------------------------------------------------
class ErroSistema(Exception):
    """Classe base das exceções do sistema."""


class ErroValidacao(ErroSistema):
    """Dado inválido segundo as regras de negócio (detectado antes de acessar o banco)."""


class ErroBancoDados(ErroSistema):
    """Falha de acesso ao banco de dados."""


class ErroIntegridade(ErroBancoDados):
    """Violação de restrição do banco (FK, UNIQUE, NOT NULL ou CHECK)."""


class RegistroNaoEncontrado(ErroBancoDados):
    """Operação sobre um registro inexistente."""


# ----------------------------------------------------------------------------------------
# Funções auxiliares de validação e normalização
# ----------------------------------------------------------------------------------------
def _limpar_texto(valor: object) -> str:
    """Normaliza Unicode (NFC), remove caracteres de controle e colapsa espaços (regra ETL-15)."""
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFC", str(valor))
    texto = "".join(" " if c in "\t\r\n" else c for c in texto if unicodedata.category(c) != "Cc" or c in "\t\r\n")
    return re.sub(r"\s+", " ", texto).strip()


def _texto_obrigatorio(valor: object, campo: str) -> str:
    texto = _limpar_texto(valor)
    if not texto:
        raise ErroValidacao(f"O campo '{campo}' é obrigatório.")
    return texto


def _texto_opcional(valor: object) -> Optional[str]:
    """Converte placeholders de planilha (ex.: 'Não consta') em None."""
    texto = _limpar_texto(valor)
    return None if texto.lower() in _PLACEHOLDERS_NULOS else texto


def _numero(valor: object, campo: str) -> float:
    """Converte para float aceitando vírgula decimal; rejeita booleanos, NaN e infinito."""
    if isinstance(valor, bool):
        raise ErroValidacao(f"O campo '{campo}' deve ser numérico.")
    try:
        numero = float(str(valor).replace(",", ".")) if isinstance(valor, str) else float(valor)
    except (TypeError, ValueError):
        raise ErroValidacao(f"O campo '{campo}' deve ser numérico (recebido: {valor!r}).") from None
    if math.isnan(numero) or math.isinf(numero):
        raise ErroValidacao(f"O campo '{campo}' deve ser um número finito.")
    return numero


def _id_positivo(valor: object, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErroValidacao(f"O campo '{campo}' deve ser um inteiro positivo (recebido: {valor!r}).")
    return valor


def _normalizar_mmc(valor: object) -> str:
    """Normaliza a grafia da MMC removendo pontos e espaços (500.011 -> 500011, regra ETL-10)."""
    codigo = _texto_obrigatorio(valor, "codigo_mmc").replace(".", "").replace(" ", "")
    if not codigo.isdigit():
        raise ErroValidacao(f"Código de MMC inválido: {valor!r}.")
    return codigo


def _validar_data(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    texto = _texto_obrigatorio(valor, "data_medicao")
    try:
        datetime.strptime(texto, FORMATO_DATA)
    except ValueError:
        raise ErroValidacao(f"Data inválida: {valor!r} (formato esperado: AAAA-MM-DD HH:MM:SS).") from None
    return texto


# ----------------------------------------------------------------------------------------
# Classes de domínio
# ----------------------------------------------------------------------------------------
class Tecnico:
    """Técnico executor das calibrações (tabela tecnico)."""

    def __init__(self, nome_tecnico: str, setor: str, id_tecnico: Optional[int] = None) -> None:
        self._id_tecnico: Optional[int] = None
        self.nome_tecnico = nome_tecnico
        self.setor = setor
        if id_tecnico is not None:
            self.id_tecnico = id_tecnico

    @property
    def id_tecnico(self) -> Optional[int]:
        return self._id_tecnico

    @id_tecnico.setter
    def id_tecnico(self, valor: int) -> None:
        """O id é atribuído pelo banco e só pode ser definido uma vez."""
        if self._id_tecnico is not None:
            raise ErroValidacao("O id do técnico já foi definido e não pode ser alterado.")
        self._id_tecnico = _id_positivo(valor, "id_tecnico")

    @property
    def nome_tecnico(self) -> str:
        return self._nome_tecnico

    @nome_tecnico.setter
    def nome_tecnico(self, valor: str) -> None:
        self._nome_tecnico = _texto_obrigatorio(valor, "nome_tecnico")

    @property
    def setor(self) -> str:
        return self._setor

    @setor.setter
    def setor(self, valor: str) -> None:
        self._setor = _texto_obrigatorio(valor, "setor")

    @classmethod
    def de_linha(cls, linha: sqlite3.Row) -> "Tecnico":
        return cls(linha["nome_tecnico"], linha["setor"], linha["id_tecnico"])

    def __repr__(self) -> str:
        return f"Tecnico(id={self._id_tecnico}, nome={self._nome_tecnico!r}, setor={self._setor!r})"


class Equipamento:
    """Instrumento calibrado pelo laboratório (tabela equipamento)."""

    def __init__(self, codigo_tag: str, nome_equipamento: str, fabricante: Optional[str] = None,
                 modelo: Optional[str] = None, id_equipamento: Optional[int] = None) -> None:
        self._id_equipamento: Optional[int] = None
        self.codigo_tag = codigo_tag
        self.nome_equipamento = nome_equipamento
        self.fabricante = fabricante
        self.modelo = modelo
        if id_equipamento is not None:
            self.id_equipamento = id_equipamento

    @property
    def id_equipamento(self) -> Optional[int]:
        return self._id_equipamento

    @id_equipamento.setter
    def id_equipamento(self, valor: int) -> None:
        """O id é atribuído pelo banco e só pode ser definido uma vez."""
        if self._id_equipamento is not None:
            raise ErroValidacao("O id do equipamento já foi definido e não pode ser alterado.")
        self._id_equipamento = _id_positivo(valor, "id_equipamento")

    @property
    def codigo_tag(self) -> str:
        return self._codigo_tag

    @codigo_tag.setter
    def codigo_tag(self, valor: str) -> None:
        """Padroniza a TAG (sem espaços nas pontas e em maiúsculas) para o UNIQUE do banco funcionar."""
        self._codigo_tag = _texto_obrigatorio(valor, "codigo_tag").upper()

    @property
    def nome_equipamento(self) -> str:
        return self._nome_equipamento

    @nome_equipamento.setter
    def nome_equipamento(self, valor: str) -> None:
        self._nome_equipamento = _texto_obrigatorio(valor, "nome_equipamento")

    @property
    def fabricante(self) -> Optional[str]:
        return self._fabricante

    @fabricante.setter
    def fabricante(self, valor: Optional[str]) -> None:
        self._fabricante = _texto_opcional(valor)

    @property
    def modelo(self) -> Optional[str]:
        return self._modelo

    @modelo.setter
    def modelo(self, valor: Optional[str]) -> None:
        self._modelo = _texto_opcional(valor)

    @classmethod
    def de_linha(cls, linha: sqlite3.Row) -> "Equipamento":
        return cls(linha["codigo_tag"], linha["nome_equipamento"], linha["fabricante"],
                   linha["modelo"], linha["id_equipamento"])

    def __repr__(self) -> str:
        return (f"Equipamento(id={self._id_equipamento}, tag={self._codigo_tag!r}, "
                f"nome={self._nome_equipamento!r})")


class Medicao:
    """
    Ensaio de calibração de um parâmetro de um equipamento (tabela medicao). Objeto IMUTÁVEL.

    Recebe os dados brutos (nominal, tolerâncias como desvios e as duas rodadas de medição) e DERIVA:
      - valor_obtido = média das duas rodadas (RN-04);
      - erro = |valor_obtido - valor_nominal| (RN-09); desvio = valor_obtido - valor_nominal (com sinal);
      - faixa aceitável = [nominal + tolerancia_min ; nominal + tolerancia_max];
      - status_resultado = APROVADO se o valor obtido estiver dentro da faixa (com margem EPSILON).

    Não há setters: um ensaio registrado não deve ser alterado depois (rastreabilidade, RN-08).
    Para corrigir um ensaio, registra-se um novo ensaio; o histórico original permanece intacto.
    """

    def __init__(self, id_equipamento: int, id_tecnico: int, setor_solicitante: str, codigo_mmc: str,
                 parametro_medido: str, valor_nominal: float, tolerancia_min: float, tolerancia_max: float,
                 medida_1: float, medida_2: float, data_medicao: Optional[str] = None,
                 id_medicao: Optional[int] = None) -> None:
        self._id_medicao: Optional[int] = None
        self._id_equipamento = _id_positivo(id_equipamento, "id_equipamento")
        self._id_tecnico = _id_positivo(id_tecnico, "id_tecnico")
        self._setor_solicitante = _texto_obrigatorio(setor_solicitante, "setor_solicitante")
        self._codigo_mmc = _normalizar_mmc(codigo_mmc)
        self._parametro_medido = _texto_obrigatorio(parametro_medido, "parametro_medido")
        self._valor_nominal = _numero(valor_nominal, "valor_nominal")
        minimo = _numero(tolerancia_min, "tolerancia_min")
        maximo = _numero(tolerancia_max, "tolerancia_max")
        if minimo > 0 or maximo < 0:
            raise ErroValidacao("Tolerâncias inválidas: exige-se tolerancia_min <= 0 <= tolerancia_max.")
        self._tolerancia_min, self._tolerancia_max = minimo, maximo
        self._medida_1 = _numero(medida_1, "medida_1")
        self._medida_2 = _numero(medida_2, "medida_2")
        self._data_medicao = _validar_data(data_medicao)
        if id_medicao is not None:
            self._id_medicao = _id_positivo(id_medicao, "id_medicao")

    # --- somente leitura ------------------------------------------------------------------
    @property
    def id_medicao(self) -> Optional[int]:
        return self._id_medicao

    @property
    def id_equipamento(self) -> int:
        return self._id_equipamento

    @property
    def id_tecnico(self) -> int:
        return self._id_tecnico

    @property
    def setor_solicitante(self) -> str:
        return self._setor_solicitante

    @property
    def codigo_mmc(self) -> str:
        return self._codigo_mmc

    @property
    def parametro_medido(self) -> str:
        return self._parametro_medido

    @property
    def valor_nominal(self) -> float:
        return self._valor_nominal

    @property
    def tolerancia_min(self) -> float:
        return self._tolerancia_min

    @property
    def tolerancia_max(self) -> float:
        return self._tolerancia_max

    @property
    def medida_1(self) -> float:
        return self._medida_1

    @property
    def medida_2(self) -> float:
        return self._medida_2

    @property
    def data_medicao(self) -> Optional[str]:
        return self._data_medicao

    def registrar_persistencia(self, id_medicao: int, data_medicao: str) -> None:
        """Chamado pelo DAO após o INSERT: guarda o id e a data atribuídos pelo banco (uma única vez)."""
        if self._id_medicao is not None:
            raise ErroValidacao("A medição já foi registrada e não pode ser alterada.")
        self._id_medicao = _id_positivo(id_medicao, "id_medicao")
        self._data_medicao = _validar_data(data_medicao)

    # --- regras de negócio (valores derivados) ---------------------------------------------
    @property
    def valor_obtido(self) -> float:
        """Média das duas rodadas de medição (RN-04)."""
        return (self._medida_1 + self._medida_2) / 2.0

    @property
    def erro(self) -> float:
        """Erro absoluto em relação ao nominal (RN-09)."""
        return abs(self.valor_obtido - self._valor_nominal)

    @property
    def desvio(self) -> float:
        """Diferença com sinal em relação ao nominal (obtido - nominal); informa o sentido do desvio."""
        return self.valor_obtido - self._valor_nominal

    @property
    def limite_inferior(self) -> float:
        return self._valor_nominal + self._tolerancia_min

    @property
    def limite_superior(self) -> float:
        return self._valor_nominal + self._tolerancia_max

    @property
    def faixa(self) -> tuple[float, float]:
        """Faixa aceitável [limite_inferior ; limite_superior]."""
        return (self.limite_inferior, self.limite_superior)

    def esta_aprovada(self) -> bool:
        """Verdadeiro se o valor obtido está dentro da faixa (limites inclusivos, com margem EPSILON)."""
        obtido = self.valor_obtido
        return (obtido >= self._valor_nominal + self._tolerancia_min - EPSILON
                and obtido <= self._valor_nominal + self._tolerancia_max + EPSILON)

    dentro_da_tolerancia = esta_aprovada  # nome alternativo

    @property
    def status_resultado(self) -> str:
        return STATUS_APROVADO if self.esta_aprovada() else STATUS_REPROVADO

    @classmethod
    def de_linha(cls, linha: sqlite3.Row) -> "Medicao":
        return cls(linha["id_equipamento"], linha["id_tecnico"], linha["setor_solicitante"],
                   linha["codigo_mmc"], linha["parametro_medido"], linha["valor_nominal"],
                   linha["tolerancia_min"], linha["tolerancia_max"], linha["medida_1"],
                   linha["medida_2"], linha["data_medicao"], linha["id_medicao"])

    def __str__(self) -> str:
        inf, sup = self.faixa
        return (f"{self._parametro_medido}: obtido {self.valor_obtido:.3f} | faixa [{inf:.3f} ; {sup:.3f}] | "
                f"desvio {self.desvio:+.3f} | erro {self.erro:.3f} -> {self.status_resultado}")

    def __repr__(self) -> str:
        return (f"Medicao(id={self._id_medicao}, parametro={self._parametro_medido!r}, "
                f"obtido={self.valor_obtido:.7f}, status={self.status_resultado})")


# ----------------------------------------------------------------------------------------
# Conexão e persistência
# ----------------------------------------------------------------------------------------
def _traduzir_erro(erro: sqlite3.Error) -> ErroBancoDados:
    """Converte exceções do sqlite3 em exceções de domínio com mensagem legível."""
    texto = str(erro)
    if isinstance(erro, sqlite3.IntegrityError):
        if "FOREIGN KEY" in texto:
            return ErroIntegridade("Violação de chave estrangeira: registro relacionado inexistente "
                                   "ou ainda referenciado por outros registros.")
        if "UNIQUE" in texto:
            return ErroIntegridade(f"Registro duplicado ({texto.split(': ', 1)[-1]}).")
        if "NOT NULL" in texto:
            return ErroIntegridade(f"Campo obrigatório ausente ({texto.split(': ', 1)[-1]}).")
        if "CHECK" in texto:
            return ErroIntegridade("Registro viola uma regra de integridade da tabela (CHECK).")
        return ErroIntegridade(texto)
    return ErroBancoDados(f"Erro no banco de dados: {texto}")


class ConexaoSQLite:
    """
    Gerencia a conexão com o SQLite: ativa as chaves estrangeiras (o PRAGMA vale por conexão),
    controla transações e traduz erros do banco. Pode ser usada como gerenciador de contexto.
    """

    def __init__(self, caminho: str | Path = ":memory:") -> None:
        self._caminho = str(caminho)
        self._cx: Optional[sqlite3.Connection] = None
        self._nivel = 0  # profundidade das transações aninhadas

    # --- ciclo de vida --------------------------------------------------------------------
    def conectar(self) -> "ConexaoSQLite":
        if self._cx is not None:
            return self
        try:
            self._cx = sqlite3.connect(self._caminho, isolation_level=None)  # transações explícitas
            self._cx.row_factory = sqlite3.Row
            self._cx.execute("PRAGMA foreign_keys = ON")
            if self._cx.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise ErroBancoDados("Não foi possível ativar as chaves estrangeiras (PRAGMA foreign_keys).")
        except sqlite3.Error as e:
            self._cx = None
            raise _traduzir_erro(e) from e
        return self

    def fechar(self) -> None:
        if self._cx is not None:
            self._cx.close()
            self._cx = None

    def __enter__(self) -> "ConexaoSQLite":
        return self.conectar()

    def __exit__(self, *_exc: object) -> None:
        self.fechar()

    @property
    def conexao(self) -> sqlite3.Connection:
        if self._cx is None:
            raise ErroBancoDados("Conexão fechada: chame conectar() ou use 'with'.")
        return self._cx

    # --- transações -----------------------------------------------------------------------
    @contextmanager
    def transacao(self) -> Iterator[None]:
        """Transação atômica: confirma (COMMIT) ao final ou desfaz (ROLLBACK) se ocorrer exceção."""
        cx = self.conexao
        externa = self._nivel == 0
        try:
            if externa:
                cx.execute("BEGIN")
            self._nivel += 1
            try:
                yield
            except BaseException:
                self._nivel -= 1
                if externa:
                    cx.execute("ROLLBACK")
                raise
            else:
                self._nivel -= 1
                if externa:
                    cx.execute("COMMIT")
        except sqlite3.Error as e:
            raise _traduzir_erro(e) from e

    # --- execução de comandos -------------------------------------------------------------
    def executar(self, sql: str, parametros: tuple = ()) -> sqlite3.Cursor:
        """Executa INSERT, UPDATE ou DELETE parametrizado dentro de uma transação."""
        try:
            with self.transacao():
                return self.conexao.execute(sql, parametros)
        except sqlite3.Error as e:
            raise _traduzir_erro(e) from e

    def consultar(self, sql: str, parametros: tuple = ()) -> list[sqlite3.Row]:
        """Executa SELECT parametrizado e retorna todas as linhas."""
        try:
            return self.conexao.execute(sql, parametros).fetchall()
        except sqlite3.Error as e:
            raise _traduzir_erro(e) from e

    def criar_esquema(self, caminho_ddl: str | Path = CAMINHO_DDL_PADRAO) -> None:
        """Cria as tabelas executando o script DDL da Entrega 02."""
        try:
            script = Path(caminho_ddl).read_text(encoding="utf-8")
        except OSError as e:
            raise ErroBancoDados(f"Não foi possível ler o script DDL: {caminho_ddl}") from e
        try:
            self.conexao.executescript(script)
            self.conexao.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error as e:
            raise _traduzir_erro(e) from e


class LogAtualizacoes:
    """
    Registro de auditoria dos UPDATEs: para cada campo alterado grava data/hora, entidade, id,
    campo, valor anterior e valor novo. Mantém os registros em memória e, se um caminho for
    informado, também os acrescenta a um arquivo de texto.
    """

    def __init__(self, caminho: Optional[str | Path] = None, reiniciar: bool = False) -> None:
        self._caminho = Path(caminho) if caminho else None
        self._registros: list[dict] = []
        if self._caminho is not None and reiniciar and self._caminho.exists():
            self._caminho.unlink()

    def registrar(self, entidade: str, identificador: object, campo: str, antes: object, depois: object) -> None:
        registro = {"data_hora": datetime.now().strftime(FORMATO_DATA), "entidade": entidade,
                    "id": identificador, "campo": campo, "antes": antes, "depois": depois}
        self._registros.append(registro)
        if self._caminho is not None:
            try:
                with open(self._caminho, "a", encoding="utf-8") as arquivo:
                    arquivo.write(self._formatar(registro) + "\n")
            except OSError as e:
                raise ErroBancoDados(f"Não foi possível gravar o log de atualizações: {self._caminho}") from e

    @staticmethod
    def _formatar(r: dict) -> str:
        return (f"{r['data_hora']} | UPDATE {r['entidade']} id={r['id']} | "
                f"{r['campo']}: {r['antes']!r} -> {r['depois']!r}")

    @property
    def registros(self) -> list[dict]:
        return list(self._registros)

    def linhas(self) -> list[str]:
        return [self._formatar(r) for r in self._registros]


class _DAOBase:
    """Base dos objetos de acesso a dados: guarda a conexão e o log de atualizações."""

    def __init__(self, conexao: ConexaoSQLite, log: Optional[LogAtualizacoes] = None) -> None:
        self._con = conexao
        self._log = log if log is not None else LogAtualizacoes()

    @property
    def log(self) -> LogAtualizacoes:
        return self._log

    @staticmethod
    def _exigir_afetado(cursor: sqlite3.Cursor, entidade: str, identificador: object) -> None:
        if cursor.rowcount == 0:
            raise RegistroNaoEncontrado(f"{entidade} com identificador {identificador!r} inexistente.")

    def _registrar_diferencas(self, entidade: str, identificador: object, anterior: object,
                              novo: object, campos: tuple[str, ...]) -> None:
        for campo in campos:
            antes, depois = getattr(anterior, campo), getattr(novo, campo)
            if antes != depois:
                self._log.registrar(entidade, identificador, campo, antes, depois)


class TecnicoDAO(_DAOBase):
    """CRUD da tabela tecnico (UPDATE registrado no log)."""

    def inserir(self, tecnico: Tecnico) -> Tecnico:
        cur = self._con.executar("INSERT INTO tecnico (nome_tecnico, setor) VALUES (?, ?)",
                                 (tecnico.nome_tecnico, tecnico.setor))
        tecnico.id_tecnico = cur.lastrowid
        return tecnico

    def buscar_por_id(self, id_tecnico: int) -> Optional[Tecnico]:
        linhas = self._con.consultar("SELECT * FROM tecnico WHERE id_tecnico = ?", (id_tecnico,))
        return Tecnico.de_linha(linhas[0]) if linhas else None

    def buscar_por_nome(self, nome: str) -> Optional[Tecnico]:
        linhas = self._con.consultar("SELECT * FROM tecnico WHERE nome_tecnico = ?", (_limpar_texto(nome),))
        return Tecnico.de_linha(linhas[0]) if linhas else None

    def listar(self) -> list[Tecnico]:
        return [Tecnico.de_linha(l) for l in self._con.consultar("SELECT * FROM tecnico ORDER BY nome_tecnico")]

    def atualizar(self, tecnico: Tecnico) -> None:
        """Atualiza nome e setor e registra no log cada campo alterado (antes -> depois)."""
        if tecnico.id_tecnico is None:
            raise ErroValidacao("Técnico sem id: insira antes de atualizar.")
        anterior = self.buscar_por_id(tecnico.id_tecnico)
        if anterior is None:
            raise RegistroNaoEncontrado(f"Técnico com identificador {tecnico.id_tecnico!r} inexistente.")
        self._con.executar("UPDATE tecnico SET nome_tecnico = ?, setor = ? WHERE id_tecnico = ?",
                           (tecnico.nome_tecnico, tecnico.setor, tecnico.id_tecnico))
        self._registrar_diferencas("tecnico", tecnico.id_tecnico, anterior, tecnico, ("nome_tecnico", "setor"))

    def atualizar_setor(self, id_tecnico: int, novo_setor: str) -> bool:
        """Atalho para alterar só o setor; devolve False se o técnico não existir."""
        tecnico = self.buscar_por_id(id_tecnico)
        if tecnico is None:
            return False
        tecnico.setor = novo_setor
        self.atualizar(tecnico)
        return True

    def excluir(self, id_tecnico: int) -> None:
        cur = self._con.executar("DELETE FROM tecnico WHERE id_tecnico = ?", (id_tecnico,))
        self._exigir_afetado(cur, "Técnico", id_tecnico)


class EquipamentoDAO(_DAOBase):
    """CRUD da tabela equipamento (UPDATE registrado no log)."""

    _CAMPOS = ("codigo_tag", "nome_equipamento", "fabricante", "modelo")

    def inserir(self, equipamento: Equipamento) -> Equipamento:
        cur = self._con.executar(
            "INSERT INTO equipamento (codigo_tag, nome_equipamento, fabricante, modelo) VALUES (?, ?, ?, ?)",
            (equipamento.codigo_tag, equipamento.nome_equipamento, equipamento.fabricante, equipamento.modelo))
        equipamento.id_equipamento = cur.lastrowid
        return equipamento

    def buscar_por_id(self, id_equipamento: int) -> Optional[Equipamento]:
        linhas = self._con.consultar("SELECT * FROM equipamento WHERE id_equipamento = ?", (id_equipamento,))
        return Equipamento.de_linha(linhas[0]) if linhas else None

    def buscar_por_tag(self, codigo_tag: str) -> Optional[Equipamento]:
        """Busca pela TAG padronizada (strip + maiúsculas), igual à gravada no cadastro."""
        linhas = self._con.consultar("SELECT * FROM equipamento WHERE codigo_tag = ?",
                                     (_limpar_texto(codigo_tag).upper(),))
        return Equipamento.de_linha(linhas[0]) if linhas else None

    def listar(self) -> list[Equipamento]:
        return [Equipamento.de_linha(l) for l in self._con.consultar("SELECT * FROM equipamento ORDER BY codigo_tag")]

    def atualizar(self, equipamento: Equipamento) -> None:
        """Atualiza o equipamento e registra no log cada campo alterado (antes -> depois)."""
        if equipamento.id_equipamento is None:
            raise ErroValidacao("Equipamento sem id: insira antes de atualizar.")
        anterior = self.buscar_por_id(equipamento.id_equipamento)
        if anterior is None:
            raise RegistroNaoEncontrado(f"Equipamento com identificador {equipamento.id_equipamento!r} inexistente.")
        self._con.executar(
            "UPDATE equipamento SET codigo_tag = ?, nome_equipamento = ?, fabricante = ?, modelo = ? "
            "WHERE id_equipamento = ?",
            (equipamento.codigo_tag, equipamento.nome_equipamento, equipamento.fabricante,
             equipamento.modelo, equipamento.id_equipamento))
        self._registrar_diferencas("equipamento", equipamento.id_equipamento, anterior, equipamento, self._CAMPOS)

    def excluir(self, id_equipamento: int) -> None:
        cur = self._con.executar("DELETE FROM equipamento WHERE id_equipamento = ?", (id_equipamento,))
        self._exigir_afetado(cur, "Equipamento", id_equipamento)


class MedicaoDAO(_DAOBase):
    """
    INSERT e SELECT da tabela medicao e consultas relacionais (JOIN) do relatório de calibração.
    Não há atualizar nem excluir: a medição é imutável (rastreabilidade, RN-08).
    """

    _SELECT_RELATORIO = """
        SELECT m.id_medicao, e.codigo_tag, e.nome_equipamento, t.nome_tecnico, m.setor_solicitante,
               m.codigo_mmc, m.parametro_medido, m.valor_nominal, m.tolerancia_min, m.tolerancia_max,
               m.valor_nominal + m.tolerancia_min AS limite_min, m.valor_nominal + m.tolerancia_max AS limite_max,
               m.medida_1, m.medida_2, m.valor_obtido, m.valor_obtido - m.valor_nominal AS desvio,
               m.erro, m.status_resultado, m.data_medicao
        FROM medicao m
        JOIN equipamento e ON e.id_equipamento = m.id_equipamento
        JOIN tecnico t ON t.id_tecnico = m.id_tecnico"""

    def inserir(self, medicao: Medicao) -> Medicao:
        colunas = ["id_equipamento", "id_tecnico", "setor_solicitante", "codigo_mmc", "parametro_medido",
                   "valor_nominal", "tolerancia_min", "tolerancia_max", "medida_1", "medida_2",
                   "valor_obtido", "erro", "status_resultado"]
        valores = [medicao.id_equipamento, medicao.id_tecnico, medicao.setor_solicitante, medicao.codigo_mmc,
                   medicao.parametro_medido, medicao.valor_nominal, medicao.tolerancia_min,
                   medicao.tolerancia_max, medicao.medida_1, medicao.medida_2, medicao.valor_obtido,
                   medicao.erro, medicao.status_resultado]
        if medicao.data_medicao is not None:  # senão vale o DEFAULT CURRENT_TIMESTAMP do banco
            colunas.append("data_medicao")
            valores.append(medicao.data_medicao)
        sql = f"INSERT INTO medicao ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})"
        with self._con.transacao():
            cur = self._con.executar(sql, tuple(valores))
            data = self._con.consultar("SELECT data_medicao FROM medicao WHERE id_medicao = ?", (cur.lastrowid,))[0][0]
            medicao.registrar_persistencia(cur.lastrowid, data)
        return medicao

    def buscar_por_id(self, id_medicao: int) -> Optional[Medicao]:
        linhas = self._con.consultar("SELECT * FROM medicao WHERE id_medicao = ?", (id_medicao,))
        return Medicao.de_linha(linhas[0]) if linhas else None

    def listar(self) -> list[Medicao]:
        return [Medicao.de_linha(l) for l in self._con.consultar("SELECT * FROM medicao ORDER BY id_medicao")]

    def listar_por_equipamento(self, id_equipamento: int) -> list[Medicao]:
        linhas = self._con.consultar("SELECT * FROM medicao WHERE id_equipamento = ? ORDER BY id_medicao",
                                     (id_equipamento,))
        return [Medicao.de_linha(l) for l in linhas]

    # --- consultas relacionais (JOIN) -----------------------------------------------------
    def relatorio_calibracao(self, codigo_tag: Optional[str] = None) -> list[sqlite3.Row]:
        """Medições com dados do equipamento e do técnico (JOIN das três tabelas)."""
        sql, parametros = self._SELECT_RELATORIO, ()
        if codigo_tag is not None:
            sql += " WHERE e.codigo_tag = ?"
            parametros = (_limpar_texto(codigo_tag).upper(),)
        return self._con.consultar(sql + " ORDER BY e.codigo_tag, m.data_medicao, m.id_medicao", parametros)

    def listar_reprovadas(self) -> list[sqlite3.Row]:
        """Medições reprovadas de todos os equipamentos (JOIN das três tabelas)."""
        return self._con.consultar(self._SELECT_RELATORIO + " WHERE m.status_resultado = 'REPROVADO' "
                                   "ORDER BY e.codigo_tag, m.id_medicao")

    def parecer_instrumento(self, codigo_tag: str) -> Optional[str]:
        """APROVADO somente se TODAS as medições do instrumento forem aprovadas; None se não houver medições."""
        linhas = self.relatorio_calibracao(codigo_tag)
        if not linhas:
            return None
        return STATUS_APROVADO if all(l["status_resultado"] == STATUS_APROVADO for l in linhas) else STATUS_REPROVADO

    def resumo_por_equipamento(self) -> list[sqlite3.Row]:
        """Totais de medições aprovadas e reprovadas por equipamento (LEFT JOIN + GROUP BY)."""
        return self._con.consultar(
            """SELECT e.codigo_tag, e.nome_equipamento, COUNT(m.id_medicao) AS total,
                      COALESCE(SUM(m.status_resultado = 'APROVADO'), 0)  AS aprovadas,
                      COALESCE(SUM(m.status_resultado = 'REPROVADO'), 0) AS reprovadas
               FROM equipamento e LEFT JOIN medicao m ON m.id_equipamento = e.id_equipamento
               GROUP BY e.id_equipamento ORDER BY e.codigo_tag""")
