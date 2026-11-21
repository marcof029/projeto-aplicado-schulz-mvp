-- Projeto Aplicado I - Schulz S.A.
-- Entrega 02 (versão revisada) - Banco de Dados SQLite
-- Professor: Hugo Menezes Barra
-- Script DDL: criação das 3 tabelas. Os dados de exemplo estão em 03b_dados_exemplo.sql.
--
-- Observação: PRAGMA foreign_keys vale por conexão no SQLite. Toda aplicação que abrir
-- o banco deve executá-lo a cada nova conexão (a Entrega 03 faz isso na classe de conexão).

PRAGMA foreign_keys = ON;

-- Tabela 1: Técnico (executor da calibração)
CREATE TABLE tecnico (
    id_tecnico   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_tecnico TEXT NOT NULL UNIQUE,
    setor        TEXT NOT NULL
);

-- Tabela 2: Equipamento (instrumento calibrado) - Ex.: TAG 703.1208
-- fabricante e modelo aceitam NULL: "Não consta" na planilha vira NULL (regra ETL-11 da Entrega 01)
CREATE TABLE equipamento (
    id_equipamento   INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_tag       TEXT NOT NULL UNIQUE,
    nome_equipamento TEXT NOT NULL,
    fabricante       TEXT,
    modelo           TEXT
);

-- Tabela 3: Medição (evento de calibração de um parâmetro de um equipamento)
-- Tolerâncias são desvios em relação ao nominal: tolerancia_min <= 0 (Lower Tol) e tolerancia_max >= 0 (Upper Tol), garantido por CHECK.
-- valor_obtido, erro e status_resultado são derivados; os CHECKs impedem gravação inconsistente.
CREATE TABLE medicao (
    id_medicao        INTEGER PRIMARY KEY AUTOINCREMENT,
    id_equipamento    INTEGER NOT NULL,
    id_tecnico        INTEGER NOT NULL,
    setor_solicitante TEXT NOT NULL,
    codigo_mmc        TEXT NOT NULL,
    parametro_medido  TEXT NOT NULL,
    valor_nominal     REAL NOT NULL,
    tolerancia_min    REAL NOT NULL,
    tolerancia_max    REAL NOT NULL,
    medida_1          REAL NOT NULL,
    medida_2          REAL NOT NULL,
    valor_obtido      REAL NOT NULL,
    erro              REAL NOT NULL,
    status_resultado  TEXT NOT NULL CHECK (status_resultado IN ('APROVADO','REPROVADO')),
    data_medicao      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_equipamento) REFERENCES equipamento (id_equipamento) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (id_tecnico)     REFERENCES tecnico (id_tecnico)         ON UPDATE RESTRICT ON DELETE RESTRICT,
    -- a zona de tolerância contém o valor nominal: Tol- <= 0 <= Tol+
    CHECK (tolerancia_min <= 0 AND tolerancia_max >= 0),
    -- valor_obtido é a média das duas rodadas de medição (RN-04)
    CHECK (ABS(valor_obtido - (medida_1 + medida_2) / 2.0) <= 1e-9),
    -- erro é o valor absoluto da diferença entre o valor obtido e o nominal (RN-09)
    CHECK (ABS(erro - ABS(valor_obtido - valor_nominal)) <= 1e-9),
    -- status: APROVADO somente se o valor obtido estiver entre nominal + Tol- e nominal + Tol+ (margem de 1e-7 contra erro de ponto flutuante)
    CHECK (status_resultado = CASE
              WHEN valor_obtido >= valor_nominal + tolerancia_min - 1e-7
               AND valor_obtido <= valor_nominal + tolerancia_max + 1e-7
              THEN 'APROVADO' ELSE 'REPROVADO' END)
);

CREATE INDEX idx_medicao_equipamento ON medicao (id_equipamento);
CREATE INDEX idx_medicao_tecnico     ON medicao (id_tecnico);
