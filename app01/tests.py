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
        content = '\xef\xbb\xbfsiRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n'
        result = parse_seq_file(BytesIO(content.encode('utf-8')))
        self.assertEqual(len(result.rows), 1)
