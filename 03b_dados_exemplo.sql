-- Dados de exemplo da Entrega 02 (versão revisada)
-- Origem: planilhas da Schulz (Entrega 01). A linha marcada como SIMULADA é fictícia e serve só para testar o status REPROVADO.

PRAGMA foreign_keys = ON;

INSERT INTO tecnico (nome_tecnico, setor) VALUES ('Jose Alcides Rosa Junior', 'Metrologia');
INSERT INTO tecnico (nome_tecnico, setor) VALUES ('Cleocir de Souza', 'Metrologia');

-- Fabricante e modelo do dispositivo 703.1208 constam como "Não consta" na planilha: gravados como NULL.
INSERT INTO equipamento (codigo_tag, nome_equipamento, fabricante, modelo)
VALUES ('703.1208', 'Dispositivo de controle', NULL, NULL);

-- Medição 1 (real): 62P_DIÂMETRO 2 -> média 6,0780814; erro 0,0030814; dentro da tolerância
INSERT INTO medicao (id_equipamento, id_tecnico, setor_solicitante, codigo_mmc, parametro_medido,
    valor_nominal, tolerancia_min, tolerancia_max, medida_1, medida_2, valor_obtido, erro, status_resultado, data_medicao)
VALUES (1, 1, 'Usinagem I', '500011', '62P_DIAMETRO_2',
    6.075, -0.01, 0.01, 6.0781314, 6.0780314, 6.0780814, 0.0030814, 'APROVADO', '2026-08-13 16:16:26');

-- Medição 2 (real): PLANICIDADE_REF -> nominal 0, Tol- 0, Tol+ 0,05; média 0,002217
INSERT INTO medicao (id_equipamento, id_tecnico, setor_solicitante, codigo_mmc, parametro_medido,
    valor_nominal, tolerancia_min, tolerancia_max, medida_1, medida_2, valor_obtido, erro, status_resultado, data_medicao)
VALUES (1, 1, 'Usinagem I', '500011', 'PLANICIDADE_REF',
    0.0, 0.0, 0.05, 0.002167, 0.002267, 0.002217, 0.002217, 'APROVADO', '2026-08-13 16:16:26');

-- Medição 3 (SIMULADA): valores fictícios fora da tolerância para exercitar o status REPROVADO
INSERT INTO medicao (id_equipamento, id_tecnico, setor_solicitante, codigo_mmc, parametro_medido,
    valor_nominal, tolerancia_min, tolerancia_max, medida_1, medida_2, valor_obtido, erro, status_resultado, data_medicao)
VALUES (1, 2, 'Usinagem I', '500011', '62P_DIAMETRO_SIMULADO',
    6.075, -0.01, 0.01, 6.0951, 6.0953, 6.0952, 0.0202, 'REPROVADO', '2026-08-14 09:30:00');
