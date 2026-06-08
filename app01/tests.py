from django.test import TestCase
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id,
)


class ParseCompoundIdTest(TestCase):
    def test_standard_2digit(self):
        project, target = _parse_compound_id('BPR_3M03FN01')
        self.assertEqual(project, '3M03')
        self.assertEqual(target, 'FN')

    def test_standard_3digit(self):
        project, target = _parse_compound_id('BPR_3M03FN001')
        self.assertEqual(project, '3M03')
        self.assertEqual(target, 'FN')

    def test_different_target(self):
        project, target = _parse_compound_id('BPR_4A01CD05')
        self.assertEqual(project, '4A01')
        self.assertEqual(target, 'CD')

    def test_unrecognized_format(self):
        project, target = _parse_compound_id('UNKNOWN_ID')
        self.assertEqual(project, '')
        self.assertEqual(target, '')


class CompoundModelTest(TestCase):
    def test_create_auto_parses_project_target(self):
        c = Compound.objects.create(compound_id='BPR_3M03FN01')
        self.assertEqual(c.project, '3M03')
        self.assertEqual(c.target, 'FN')

    def test_str(self):
        c = Compound(compound_id='BPR_3M03FN01')
        self.assertEqual(str(c), 'BPR_3M03FN01')


class StrandModelTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR_3M03FN01')

    def test_create_ss_strand(self):
        s = Strand.objects.create(
            compound=self.compound,
            strand_type='SS',
            sequence_id='BPR_3M03FN01_SS',
            modify_seq='mAmGfUmA',
        )
        self.assertEqual(s.strand_type, 'SS')
        self.assertEqual(s.compound.compound_id, 'BPR_3M03FN01')

    def test_unique_together(self):
        Strand.objects.create(compound=self.compound, strand_type='SS')
        with self.assertRaises(Exception):
            Strand.objects.create(compound=self.compound, strand_type='SS')


class ExperimentAndDataPointTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR_3M03FN01')
        self.exp = Experiment.objects.create(
            compound=self.compound,
            exp_type='in_vitro',
            assay_name='FASN knockdown Hepa1-6',
            cell_line='Hepa1-6',
            batch_label='2026-05',
        )

    def test_datapoint_creation(self):
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=100.0,
            x_type='concentration',
            replicate='A',
            value=0.26,
            readout_type='mRNA_remaining',
        )
        self.assertFalse(dp.is_control)
        self.assertFalse(dp.is_flagged)
        self.assertIsNone(dp.raw_cp)

    def test_datapoint_with_raw_cp(self):
        raw = {
            'reference_gene': 'GAPDH',
            'target_gene': 'FASN',
            'cp_values': {
                'GAPDH': {'A': 16.06, 'B': 16.18, 'C': 16.07},
                'FASN': {'A': 23.85, 'B': 23.85, 'C': 23.81},
            },
            'computed': {'GAPDH_mean': 16.07, 'GAPDH_cv': 0.05,
                         'FASN_mean': 23.85, 'FASN_cv': 0.02},
        }
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=100.0, x_type='concentration',
            replicate='A', value=0.26,
            readout_type='mRNA_remaining',
            raw_cp=raw,
        )
        self.assertEqual(dp.raw_cp['reference_gene'], 'GAPDH')
        self.assertAlmostEqual(dp.raw_cp['cp_values']['GAPDH']['A'], 16.06)

    def test_flagged_datapoint(self):
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=56, x_type='timepoint',
            replicate='2', value=-54.22,
            readout_type='knockdown_pct',
            is_flagged=True, flag_note='outlier *',
        )
        self.assertTrue(dp.is_flagged)

    def test_experiment_summary(self):
        s = ExperimentSummary.objects.create(
            experiment=self.exp,
            max_kd_pct=74.71,
            ic50_nm=5.48,
            rank=9,
        )
        self.assertAlmostEqual(s.ic50_nm, 5.48)
        self.assertEqual(self.exp.summary.rank, 9)


from io import BytesIO
from app01.upload_pipeline import (
    detect_id_format, normalize_compound_ids, parse_seq_file,
)



class DetectIdFormatTest(TestCase):
    def test_all_2digit(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN01', 'BPR_3M03FN02']), '2-digit')

    def test_all_3digit(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN001', 'BPR_3M03FN002']), '3-digit')

    def test_mixed(self):
        self.assertEqual(detect_id_format(['BPR_3M03FN01', 'BPR_3M03FN002']), 'mixed')

    def test_empty_returns_2digit(self):
        self.assertEqual(detect_id_format([]), '2-digit')

    def test_non_bpr_ids_return_2digit(self):
        self.assertEqual(detect_id_format(['Mock', 'Neg_ctrl']), '2-digit')


class NormalizeCompoundIdsTest(TestCase):
    def test_3digit_to_2digit(self):
        self.assertEqual(normalize_compound_ids(['BPR_3M03FN001'], '2-digit'), ['BPR_3M03FN01'])

    def test_2digit_to_3digit(self):
        self.assertEqual(normalize_compound_ids(['BPR_3M03FN01'], '3-digit'), ['BPR_3M03FN001'])

    def test_non_bpr_ids_unchanged(self):
        self.assertEqual(normalize_compound_ids(['OTHER_ID'], '2-digit'), ['OTHER_ID'])

    def test_multiple_ids(self):
        result = normalize_compound_ids(['BPR_3M03FN001', 'BPR_3M03FN002'], '2-digit')
        self.assertEqual(result, ['BPR_3M03FN01', 'BPR_3M03FN02'])

    def test_large_serial_unchanged_for_2digit(self):
        self.assertEqual(normalize_compound_ids(['BPR_3M03FN100'], '2-digit'), ['BPR_3M03FN100'])


class ParseSeqFileTest(TestCase):
    SEQ_CSV = (
        'siRNAID,SS,AS\n'
        'BPR_3M03FN001,GmGmGmGmAmAmAfC,AmCfUmUmdUGmdCC\n'
        'BPR_3M03FN002,UmUmGmUmGmGmCfC,UmUfAmCmdAGmdAG\n'
    )

    def test_parse_rows(self):
        result = parse_seq_file(BytesIO(self.SEQ_CSV.encode()))
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0]['compound_id'], 'BPR_3M03FN001')
        self.assertEqual(result.rows[0]['ss_seq'], 'GmGmGmGmAmAmAfC')
        self.assertEqual(result.rows[0]['as_seq'], 'AmCfUmUmdUGmdCC')

    def test_id_format_detected_as_3digit(self):
        result = parse_seq_file(BytesIO(self.SEQ_CSV.encode()))
        self.assertEqual(result.id_format, '3-digit')

    def test_skips_empty_rows(self):
        csv_content = 'siRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n,,\n'
        result = parse_seq_file(BytesIO(csv_content.encode()))
        self.assertEqual(len(result.rows), 1)

    def test_bom_handled(self):
        content = b'\xef\xbb\xbf' + b'siRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n'
        result = parse_seq_file(BytesIO(content))
        self.assertEqual(len(result.rows), 1)


from app01.upload_pipeline import parse_summary_csv


class ParseSummaryCsvTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
        '3,siRNA-01,10,0.47,0.53,0.50,,2,siRNA-02,BPR_3M03FN02,72.39,8.22,10\n'
        '4,siRNA-02,100,0.25,0.30,0.28,,,,,,,\n'
    )

    def setUp(self):
        self.result = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))

    def test_assay_name_extracted(self):
        self.assertEqual(self.result.assay_name, 'FASN mRNA')

    def test_mapping_extracted(self):
        self.assertEqual(self.result.mapping['siRNA-01'], 'BPR_3M03FN01')
        self.assertEqual(self.result.mapping['siRNA-02'], 'BPR_3M03FN02')

    def test_summaries_extracted(self):
        s = next(x for x in self.result.summaries if x['compound_id'] == 'BPR_3M03FN01')
        self.assertAlmostEqual(s['max_kd_pct'], 74.71)
        self.assertAlmostEqual(s['ic50_nm'], 5.48)
        self.assertEqual(s['rank'], 9)

    def test_datapoints_compound_id_resolved(self):
        dp = next(d for d in self.result.datapoints
                  if d['compound_id'] == 'BPR_3M03FN01'
                  and d['x_value'] == 100.0 and d['replicate'] == 'A')
        self.assertAlmostEqual(dp['value'], 0.26)
        self.assertFalse(dp['is_control'])
        self.assertEqual(dp['readout_type'], 'mRNA_remaining')

    def test_datapoints_per_siRNA_dose(self):
        # siRNA-01 at 100nM → 3 DataPoints (A, B, Mean)
        dps = [d for d in self.result.datapoints
               if d['compound_id'] == 'BPR_3M03FN01' and d['x_value'] == 100.0]
        reps = {d['replicate'] for d in dps}
        self.assertEqual(reps, {'A', 'B', 'Mean'})

    def test_mock_values_captured(self):
        self.assertAlmostEqual(self.result.mock_values.get('A'), 1.07)
        self.assertAlmostEqual(self.result.mock_values.get('B'), 0.94)
        self.assertAlmostEqual(self.result.mock_values.get('Mean'), 1.01)

    def test_invalid_format_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_summary_csv(BytesIO(b'not,a,summary,file\n1,2,3\n'))


from app01.upload_pipeline import parse_cp_file, enrich_datapoints_with_cp


class ParseCpFileTest(TestCase):
    # Simplified version of the real Prism two-step RT-qPCR format
    CP_CSV = (
        '\n'
        'Two step RT-qPCR study in Hepa1-6 cells (Day 1)\n'
        ',,,Cp value,,,,,,GAPDH,,,FASN\n'
        ',ID,Dose,GAPDH,,,FASN\n'
        '#,,,A,B,C,A,B,C\n'
        '1,siRNA-01,100,16.06,16.18,16.07,23.85,23.85,23.81\n'
        '2,siRNA-01,10,15.95,16.07,15.95,23.16,22.91,22.85\n'
        '9,siRNA-01,100,16.17,16.12,16.43,24.00,24.01,23.95\n'
        '10,siRNA-01,10,16.20,16.21,16.44,23.18,22.95,22.97\n'
    )

    def setUp(self):
        self.result = parse_cp_file(BytesIO(self.CP_CSV.encode()))

    def test_assay_name_extracted(self):
        self.assertIn('Hepa1-6', self.result.assay_name)

    def test_genes_detected(self):
        self.assertEqual(self.result.reference_gene, 'GAPDH')
        self.assertEqual(self.result.target_gene, 'FASN')

    def test_rep_a_cp_values(self):
        key = ('siRNA-01', 100.0)
        self.assertIn(key, self.result.cp_data)
        rep_a = self.result.cp_data[key]['rep_A']
        self.assertEqual(rep_a['GAPDH']['A'], 16.06)
        self.assertEqual(rep_a['FASN']['C'], 23.81)

    def test_rep_b_cp_values(self):
        key = ('siRNA-01', 100.0)
        rep_b = self.result.cp_data[key]['rep_B']
        self.assertEqual(rep_b['GAPDH']['A'], 16.17)
        self.assertEqual(rep_b['FASN']['A'], 24.00)

    def test_second_dose_also_parsed(self):
        self.assertIn(('siRNA-01', 10.0), self.result.cp_data)


class EnrichDatapointsWithCpTest(TestCase):
    def test_enriches_rep_a_and_b(self):
        datapoints = [
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'A',
             'x_type': 'concentration', 'value': 0.26, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'B',
             'x_type': 'concentration', 'value': 0.25, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
            {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'Mean',
             'x_type': 'concentration', 'value': 0.255, 'is_control': False,
             'readout_type': 'mRNA_remaining', 'raw_cp': None},
        ]
        cp_data = {
            ('siRNA-01', 100.0): {
                'rep_A': {'GAPDH': {'A': 16.06, 'B': 16.18, 'C': 16.07},
                          'FASN': {'A': 23.85, 'B': 23.85, 'C': 23.81}},
                'rep_B': {'GAPDH': {'A': 16.17, 'B': 16.12, 'C': 16.43},
                          'FASN': {'A': 24.00, 'B': 24.01, 'C': 23.95}},
            }
        }
        mapping = {'siRNA-01': 'BPR_3M03FN01'}
        result = enrich_datapoints_with_cp(datapoints, cp_data, mapping)
        rep_a = next(d for d in result if d['replicate'] == 'A')
        rep_b = next(d for d in result if d['replicate'] == 'B')
        rep_m = next(d for d in result if d['replicate'] == 'Mean')
        self.assertIsNotNone(rep_a['raw_cp'])
        self.assertIsNotNone(rep_b['raw_cp'])
        self.assertIsNone(rep_m['raw_cp'])
        self.assertEqual(rep_a['raw_cp']['GAPDH']['A'], 16.06)
        self.assertEqual(rep_b['raw_cp']['GAPDH']['A'], 16.17)
