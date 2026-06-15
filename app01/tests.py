from django.test import TestCase
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id, LmsUser,
    ExperimentAttachment,
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

    def test_non_default_genes_detected(self):
        csv_content = (
            '\n'
            'Study in B2M cells\n'
            ',ID,Dose,B2M,,,LDLR\n'
            '#,,,A,B,C,A,B,C\n'
            '1,siRNA-01,100,15.0,15.1,15.2,22.0,22.1,22.2\n'
            '2,siRNA-01,100,15.3,15.4,15.5,22.3,22.4,22.5\n'
        )
        result = parse_cp_file(BytesIO(csv_content.encode()))
        self.assertEqual(result.reference_gene, 'B2M')
        self.assertEqual(result.target_gene, 'LDLR')

    def test_third_occurrence_ignored(self):
        csv_content = (
            '\n'
            'Title\n'
            ',ID,Dose,GAPDH,,,FASN\n'
            '#,,,A,B,C,A,B,C\n'
            '1,siRNA-01,100,16.0,16.0,16.0,23.0,23.0,23.0\n'
            '2,siRNA-01,100,16.1,16.1,16.1,23.1,23.1,23.1\n'
            '3,siRNA-01,100,99.9,99.9,99.9,99.9,99.9,99.9\n'  # should be ignored
        )
        result = parse_cp_file(BytesIO(csv_content.encode()))
        key = ('siRNA-01', 100.0)
        self.assertEqual(result.cp_data[key]['rep_B']['GAPDH']['A'], 16.1)


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

    def test_unmapped_compound_raw_cp_stays_none(self):
        dp = {'compound_id': 'BPR_UNKNOWN', 'x_value': 100.0, 'replicate': 'A',
              'x_type': 'concentration', 'value': 0.5, 'is_control': False,
              'readout_type': 'mRNA_remaining', 'raw_cp': None}
        result = enrich_datapoints_with_cp([dp], {}, {})
        self.assertIsNone(result[0]['raw_cp'])

    def test_no_cp_data_for_key_stays_none(self):
        dp = {'compound_id': 'BPR_3M03FN01', 'x_value': 100.0, 'replicate': 'A',
              'x_type': 'concentration', 'value': 0.26, 'is_control': False,
              'readout_type': 'mRNA_remaining', 'raw_cp': None}
        mapping = {'siRNA-01': 'BPR_3M03FN01'}
        result = enrich_datapoints_with_cp([dp], {}, mapping)
        self.assertIsNone(result[0]['raw_cp'])


from django.test import Client
from app01.upload_pipeline import detect_existing_compounds, build_preview


class DetectExistingCompoundsTest(TestCase):
    def setUp(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        Compound.objects.create(compound_id='BPR_3M03FN02')

    def test_separates_existing_and_new(self):
        result = detect_existing_compounds(['BPR_3M03FN01', 'BPR_3M03FN03'])
        self.assertIn('BPR_3M03FN01', result['existing'])
        self.assertIn('BPR_3M03FN03', result['new'])
        self.assertNotIn('BPR_3M03FN03', result['existing'])

    def test_all_new(self):
        result = detect_existing_compounds(['BPR_3M03FN99'])
        self.assertEqual(result['existing'], [])
        self.assertEqual(result['new'], ['BPR_3M03FN99'])

    def test_empty_input(self):
        result = detect_existing_compounds([])
        self.assertEqual(result['existing'], [])
        self.assertEqual(result['new'], [])


class BuildPreviewTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
    )

    def setUp(self):
        self.summary_parsed = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))

    def test_new_compound_detected(self):
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        cids = [c['compound_id'] for c in preview['new_compounds']]
        self.assertIn('BPR_3M03FN01', cids)

    def test_existing_compound_detected(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        self.assertIn('BPR_3M03FN01', preview['existing_compounds'])

    def test_experiments_built(self):
        preview = build_preview(None, self.summary_parsed, [], '2026-05', 'FASN test')
        self.assertEqual(len(preview['experiments']), 1)
        exp = preview['experiments'][0]
        self.assertEqual(exp['compound_id'], 'BPR_3M03FN01')
        self.assertEqual(exp['exp_type'], 'in_vitro')
        self.assertIn('summary', exp)

    def test_warning_for_existing_compound(self):
        Compound.objects.create(compound_id='BPR_3M03FN01')
        preview = build_preview(None, self.summary_parsed, [], '2026-05', '')
        self.assertTrue(any('BPR_3M03FN01' in w for w in preview['warnings']))

    def test_id_format_conflict_detected(self):
        seq_csv = 'siRNAID,SS,AS\nBPR_3M03FN001,Gm,Am\n'
        seq_parsed = parse_seq_file(BytesIO(seq_csv.encode()))  # 3-digit
        # summary has BPR_3M03FN01 (2-digit)
        preview = build_preview(seq_parsed, self.summary_parsed, [], '2026-05', '')
        self.assertTrue(preview['id_format_conflict'])

    def test_no_files_yields_error(self):
        preview = build_preview(None, None, [], '2026-05', '')
        self.assertTrue(len(preview['errors']) > 0)


class UploadViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        LmsUser.objects.create_user(
            username='uploader', password='pass123', user_type='data_admin'
        )
        self.client.login(username='uploader', password='pass123')

    def test_get_upload_page_returns_200(self):
        response = self.client.get('/upload/')
        self.assertEqual(response.status_code, 200)

    def test_get_requires_login(self):
        self.client.logout()
        response = self.client.get('/upload/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_post_without_files_shows_error(self):
        response = self.client.post('/upload/', {'batch_label': '2026-05'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '请至少上传')

    def test_post_seq_file_stores_session_and_redirects(self):
        csv_content = b'siRNAID,SS,AS\nBPR_3M03FN01,GmGm,AmCf\n'
        response = self.client.post('/upload/', {
            'seq_file': BytesIO(csv_content),
            'batch_label': '2026-05',
        }, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('upload_preview', self.client.session)

    def test_post_missing_batch_label_shows_error(self):
        csv_content = b'siRNAID,SS,AS\nBPR_3M03FN01,GmGm,AmCf\n'
        response = self.client.post('/upload/', {
            'seq_file': BytesIO(csv_content),
            'batch_label': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '批次名称为必填项')


class UploadConfirmViewTest(TestCase):
    SUMMARY_CSV = (
        '\n'
        ',,,FASN mRNA\n'
        '#,ID,Dose (nM),A,B,Mean,,#,ID,Name,Max KD,IC50 (nM),Rank\n'
        '1,Mock,Mock,1.07,0.94,1.01,,,,,,,\n'
        '2,siRNA-01,100,0.26,0.25,0.25,,1,siRNA-01,BPR_3M03FN01,74.71,5.48,9\n'
    )

    def setUp(self):
        self.client = Client()
        LmsUser.objects.create_user(
            username='confirmer', password='pass123', user_type='data_admin'
        )
        self.client.login(username='confirmer', password='pass123')
        # Pre-populate session with parsed preview
        summary_parsed = parse_summary_csv(BytesIO(self.SUMMARY_CSV.encode()))
        preview = build_preview(None, summary_parsed, [], '2026-05', 'FASN test')
        session = self.client.session
        session['upload_preview'] = preview
        session.save()

    def test_confirm_creates_compound_and_experiment(self):
        response = self.client.post('/upload/confirm/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Compound.objects.filter(compound_id='BPR_3M03FN01').exists())
        self.assertTrue(Experiment.objects.filter(batch_label='2026-05').exists())

    def test_confirm_creates_datapoints(self):
        self.client.post('/upload/confirm/', follow=True)
        exp = Experiment.objects.get(batch_label='2026-05')
        self.assertTrue(exp.datapoints.filter(x_value=100.0, replicate='A').exists())

    def test_confirm_creates_experiment_summary(self):
        self.client.post('/upload/confirm/', follow=True)
        exp = Experiment.objects.get(batch_label='2026-05')
        self.assertAlmostEqual(exp.summary.ic50_nm, 5.48)
        self.assertEqual(exp.summary.rank, 9)

    def test_confirm_clears_session(self):
        self.client.post('/upload/confirm/', follow=True)
        self.assertNotIn('upload_preview', self.client.session)

    def test_confirm_without_session_redirects(self):
        session = self.client.session
        del session['upload_preview']
        session.save()
        response = self.client.post('/upload/confirm/')
        self.assertEqual(response.status_code, 302)


# ---- BuildInvivoSummaryTest ----
class BuildInvivoSummaryTest(TestCase):
    def _make_exp(self, compound_id, batch_label, datapoints):
        """
        datapoints: list of (x_value, replicate, value)
        返回一个带 .datapoints.all() mock 的 MagicMock Experiment
        """
        from unittest.mock import MagicMock
        dp_objs = []
        for x_val, rep, val in datapoints:
            dp = MagicMock()
            dp.x_value = x_val
            dp.replicate = rep
            dp.readout_type = 'knockdown_pct'
            dp.value = val
            dp_objs.append(dp)
        exp = MagicMock()
        exp.compound_id = compound_id
        exp.batch_label = batch_label
        exp.datapoints.all.return_value = dp_objs
        return exp

    def test_mean_replicate_used(self):
        from app01.views import build_invivo_summary
        exp = self._make_exp('CMP001', 'B1', [
            (7.0, 'Mean', 80.0),
            (7.0, 'A', 70.0),
            (7.0, 'B', 75.0),
            (14.0, 'Mean', 60.0),
        ])
        result = build_invivo_summary([exp])
        self.assertIn('CMP001', result)
        tps = result['CMP001'][0]['timepoints']
        self.assertEqual(len(tps), 2)
        self.assertAlmostEqual(tps[0]['kd_pct'], 80.0)
        self.assertAlmostEqual(tps[1]['kd_pct'], 60.0)

    def test_ab_fallback(self):
        from app01.views import build_invivo_summary
        exp = self._make_exp('CMP002', 'B1', [
            (7.0, 'A', 70.0),
            (7.0, 'B', 80.0),
            (14.0, 'A', 50.0),
        ])
        result = build_invivo_summary([exp])
        tps = result['CMP002'][0]['timepoints']
        self.assertAlmostEqual(tps[0]['kd_pct'], 75.0)
        self.assertAlmostEqual(tps[1]['kd_pct'], 50.0)

    def test_sorted_by_day(self):
        from app01.views import build_invivo_summary
        exp = self._make_exp('CMP003', 'B1', [
            (21.0, 'Mean', 40.0),
            (7.0, 'Mean', 80.0),
            (14.0, 'Mean', 60.0),
        ])
        result = build_invivo_summary([exp])
        days = [tp['day'] for tp in result['CMP003'][0]['timepoints']]
        self.assertEqual(days, [7.0, 14.0, 21.0])

    def test_no_knockdown_datapoints(self):
        from app01.views import build_invivo_summary
        from unittest.mock import MagicMock
        dp = MagicMock()
        dp.x_value = 7.0
        dp.replicate = 'Mean'
        dp.readout_type = 'mRNA_remaining'
        dp.value = 30.0
        exp = MagicMock()
        exp.compound_id = 'CMP004'
        exp.batch_label = 'B1'
        exp.datapoints.all.return_value = [dp]
        result = build_invivo_summary([exp])
        self.assertNotIn('CMP004', result)


# ---- CompoundListViewTest ----
class CompoundListViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='tester', password='pass', user_type='admin'
        )
        self.client.login(username='tester', password='pass')

        self.c1 = Compound.objects.create(
            compound_id='BPR_3M03FN01', project='3M03', target='FN', target_name='FASN'
        )
        self.c2 = Compound.objects.create(
            compound_id='BPR_3M03FN02', project='3M03', target='FN', target_name='FASN'
        )
        self.c3 = Compound.objects.create(
            compound_id='BPR_5X01TT01', project='5X01', target='TT', target_name='PCSK9'
        )
        self.exp_vitro = Experiment.objects.create(
            compound=self.c1, exp_type='in_vitro', assay_name='test', batch_label='B20260615'
        )
        ExperimentSummary.objects.create(experiment=self.exp_vitro, ic50_nm=2.0, max_kd_pct=85.0)
        DataPoint.objects.create(
            experiment=self.exp_vitro, x_value=100.0, x_type='concentration',
            replicate='Mean', value=0.25, readout_type='mRNA_remaining'
        )
        self.exp_vivo = Experiment.objects.create(
            compound=self.c1, exp_type='in_vivo', assay_name='mouse',
            batch_label='M20260615', time_unit='day'
        )
        DataPoint.objects.create(
            experiment=self.exp_vivo, x_value=7.0, x_type='timepoint',
            replicate='1', value=-75.0, readout_type='knockdown_pct'
        )
        DataPoint.objects.create(
            experiment=self.exp_vivo, x_value=7.0, x_type='timepoint',
            replicate='2', value=-77.0, readout_type='knockdown_pct'
        )

    def test_list_returns_200(self):
        resp = self.client.get('/compounds/')
        self.assertEqual(resp.status_code, 200)

    def test_list_requires_login(self):
        self.client.logout()
        resp = self.client.get('/compounds/')
        self.assertRedirects(resp, '/login/?next=/compounds/', fetch_redirect_response=False)

    def test_compound_data_in_context(self):
        resp = self.client.get('/compounds/')
        self.assertIn('compound_data', resp.context)
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_3M03FN01', ids)

    def test_filter_by_project(self):
        resp = self.client.get('/compounds/?project=5X01')
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_5X01TT01', ids)
        self.assertNotIn('BPR_3M03FN01', ids)

    def test_filter_by_tag_invitro(self):
        resp = self.client.get('/compounds/?tag=in_vitro')
        # c3 has no experiments, c1 has vitro → c1 present, c3 absent
        ids = [item['compound'].compound_id for item in resp.context['compound_data']]
        self.assertIn('BPR_3M03FN01', ids)
        self.assertNotIn('BPR_5X01TT01', ids)

    def test_batch_groups_in_compound_data(self):
        resp = self.client.get('/compounds/')
        item = next(
            d for d in resp.context['compound_data']
            if d['compound'].compound_id == 'BPR_3M03FN01'
        )
        self.assertGreaterEqual(len(item['batch_groups']), 1)
        first_group = item['batch_groups'][0]
        self.assertIn('rows', first_group)
        self.assertIn('attachments', first_group)

    def test_pagination_20_per_page(self):
        for i in range(22):
            Compound.objects.create(compound_id=f'BPR_PADN{i:02d}')
        resp = self.client.get('/compounds/')
        self.assertEqual(len(resp.context['compound_data']), 20)


# ---- CompoundDetailViewTest ----
class CompoundDetailViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='tester2', password='pass', user_type='admin'
        )
        self.client.login(username='tester2', password='pass')

        self.cmp = Compound.objects.create(
            compound_id='BPR_TEST01', project='TEST', target='FN'
        )
        Strand.objects.create(
            compound=self.cmp, strand_type='SS', modify_seq='mA·fU·mC'
        )
        Strand.objects.create(
            compound=self.cmp, strand_type='AS', modify_seq='fG·mA·fU'
        )
        # 体外实验 + summary + datapoints
        self.vitro_exp = Experiment.objects.create(
            compound=self.cmp, exp_type='in_vitro',
            assay_name='HeLa', batch_label='2026-03'
        )
        ExperimentSummary.objects.create(
            experiment=self.vitro_exp, ic50_nm=1.26, max_kd_pct=82.0
        )
        for x, rep, rtype, val in [
            (0.01, 'Mean', 'mRNA_remaining', 95.0),
            (0.1,  'Mean', 'mRNA_remaining', 70.0),
            (1.0,  'Mean', 'mRNA_remaining', 30.0),
            (10.0, 'Mean', 'mRNA_remaining', 8.0),
            (0.01, 'Mean', 'knockdown_pct',   5.0),
            (0.1,  'Mean', 'knockdown_pct',  30.0),
            (1.0,  'Mean', 'knockdown_pct',  70.0),
            (10.0, 'Mean', 'knockdown_pct',  92.0),
        ]:
            DataPoint.objects.create(
                experiment=self.vitro_exp,
                x_value=x, x_type='concentration',
                replicate=rep, readout_type=rtype, value=val
            )
        # 体内实验 + datapoints
        self.vivo_exp = Experiment.objects.create(
            compound=self.cmp, exp_type='in_vivo',
            assay_name='mouse', batch_label='2026-05'
        )
        for day, val in [(7.0, 76.0), (14.0, 68.0), (21.0, 52.0)]:
            DataPoint.objects.create(
                experiment=self.vivo_exp,
                x_value=day, x_type='timepoint',
                replicate='Mean', readout_type='knockdown_pct', value=val
            )

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get('/compounds/BPR_TEST01/')
        self.assertRedirects(resp, '/login/?next=/compounds/BPR_TEST01/',
                             fetch_redirect_response=False)

    def test_404_for_unknown_compound(self):
        resp = self.client.get('/compounds/NOTEXIST/')
        self.assertEqual(resp.status_code, 404)

    def test_returns_200_with_context(self):
        resp = self.client.get('/compounds/BPR_TEST01/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['compound'].compound_id, 'BPR_TEST01')
        self.assertEqual(len(resp.context['strands']), 2)
        self.assertEqual(len(resp.context['vitro_batches']), 1)
        self.assertEqual(len(resp.context['vitro_chart_data']), 1)
        self.assertEqual(len(resp.context['invivo_batches']), 1)
        batch = resp.context['invivo_batches'][0]
        self.assertEqual(batch['batch_label'], '2026-05')
        self.assertEqual(len(batch['timepoints']), 3)

    def test_vitro_chart_data_structure(self):
        resp = self.client.get('/compounds/BPR_TEST01/')
        chart = resp.context['vitro_chart_data'][0]
        self.assertEqual(chart['batch_label'], '2026-03')
        self.assertAlmostEqual(float(chart['ic50_nm']), 1.26)
        self.assertEqual(len(chart['mrna_mean']), 4)
        self.assertEqual(len(chart['kd_mean']), 4)
        self.assertEqual(chart['mrna_a'], [])

    def test_no_vitro_data(self):
        cmp2 = Compound.objects.create(compound_id='BPR_EMPTY01')
        resp = self.client.get('/compounds/BPR_EMPTY01/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(list(resp.context['vitro_batches']), [])
        self.assertEqual(resp.context['invivo_batches'], [])


# ---- UserProfileViewTest ----
class UserProfileViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='profiler', password='testpass123',
            user_type='admin', permissions_project='3M03,4A01'
        )
        self.client.login(username='profiler', password='testpass123')

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get('/profile/')
        self.assertRedirects(resp, '/login/?next=/profile/',
                             fetch_redirect_response=False)

    def test_returns_200(self):
        resp = self.client.get('/profile/')
        self.assertEqual(resp.status_code, 200)

    def test_context_has_projects(self):
        resp = self.client.get('/profile/')
        self.assertEqual(resp.context['projects'], ['3M03', '4A01'])

    def test_password_change_success(self):
        resp = self.client.post('/profile/', {
            'old_password': 'testpass123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['msg'][0], 'success')
        self.assertTrue(
            LmsUser.objects.get(username='profiler').check_password('newpass456')
        )

    def test_password_change_wrong_old(self):
        resp = self.client.post('/profile/', {
            'old_password': 'wrongpass',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        })
        self.assertEqual(resp.context['msg'][0], 'error')
        self.assertTrue(
            LmsUser.objects.get(username='profiler').check_password('testpass123')
        )

    def test_password_change_mismatch(self):
        resp = self.client.post('/profile/', {
            'old_password': 'testpass123',
            'new_password': 'newpass456',
            'confirm_password': 'different789',
        })
        self.assertEqual(resp.context['msg'][0], 'error')


import io as _io
from app01.upload_pipeline import (
    parse_transfection_file, ParsedTransfectionFile, ParsedSummary,
)


TRANSFECTION_CSV = """\
Transfection in Hepa1-6,,,,,,,,,,,,,,,,,
Plate1,1,2,3,4,5,6,7,8,9,10,11,12,Dose (nM),,#,ID,Name
A,siRNA-01,siRNA-01,siRNA-02,siRNA-02,siRNA-03,siRNA-03,siRNA-04,siRNA-04,siRNA-05,siRNA-05,Mock,,100,,1,siRNA-01,BPR_3M03FN01
B,siRNA-01,siRNA-01,siRNA-02,siRNA-02,siRNA-03,siRNA-03,siRNA-04,siRNA-04,siRNA-05,siRNA-05,Mock,,10,,2,siRNA-02,BPR_3M03FN02
,,,,,,,,,,,,,,,3,siRNA-03,BPR_3M03FN03
Plate2,1,2,3,4,5,6,7,8,9,10,11,12,Dose (nM),,4,siRNA-04,BPR_3M03FN04
A,siRNA-06,siRNA-06,siRNA-07,siRNA-07,siRNA-08,siRNA-08,siRNA-09,siRNA-09,siRNA-10,siRNA-10,Mock,,100,,5,siRNA-05,BPR_3M03FN05
,,,,,,,,,,,,,,,6,siRNA-06,BPR_3M03FN06
Tube A,Reagent,Volume,* 290 wells,,#,Stock,Dose,Add volume,Serial,,, Items,Parameters,,,,
,Opti-MEM,24.6,7134,,1,20,100,1,01:10,,,Cells,Hepa1-6,,,,
,RNAiMAX,0.4,116,,2,2,10,1,,,,Seeding,20k/well,,,,
,,,,,3,0.2,1,1,,,,Plate,96-well,,,,
Tube B,Reagent,Volume,* 3 wells,,4,0.02,0.1,1,,,,Duration,24h,,,,
,Opti-MEM,24,72,,5,0.002,0.01,1,,,,Analysis,RT-qPCR,,,,
,siRNA,1,3,,6,0.0002,0.001,1,,,,Primer,FASN/GAPDH,,,,
"""


class ParseTransfectionFileTest(TestCase):
    def _parse(self, csv_text=TRANSFECTION_CSV):
        class F:
            def read(self_):
                return csv_text.encode('utf-8')
        return parse_transfection_file(F())

    def test_cell_line_from_title(self):
        result = self._parse()
        self.assertEqual(result.cell_line, 'Hepa1-6')

    def test_notes_assembled(self):
        result = self._parse()
        self.assertIn('Seeding: 20k/well', result.notes)
        self.assertIn('Duration: 24h', result.notes)
        self.assertIn('Analysis: RT-qPCR', result.notes)
        self.assertIn('Primer: FASN/GAPDH', result.notes)

    def test_mapping_extracted(self):
        result = self._parse()
        self.assertEqual(result.mapping.get('siRNA-01'), 'BPR_3M03FN01')
        self.assertEqual(result.mapping.get('siRNA-06'), 'BPR_3M03FN06')

    def test_malformed_file_returns_empty(self):
        result = self._parse('garbage,data\nno match here\n')
        self.assertEqual(result.cell_line, '')
        self.assertEqual(result.notes, '')
        self.assertEqual(result.mapping, {})

    def test_cell_line_from_title_only(self):
        """Title row extracted when Parameters table has no Cells row."""
        csv_text = (
            'Transfection in HepG2' + ',' * 17 + '\n'
            + ',' * 12 + 'Items,Parameters' + ',' * 3 + '\n'
            + ',' * 12 + 'Seeding,50k/well' + ',' * 3 + '\n'
        )
        class F:
            def read(self_):
                return csv_text.encode('utf-8')
        result = parse_transfection_file(F())
        self.assertEqual(result.cell_line, 'HepG2')


class TransfectionIntegrationTest(TestCase):
    def _make_summary(self):
        return ParsedSummary(
            assay_name='FASN mRNA',
            mapping={'siRNA-01': 'BPR_3M03FN01'},
            datapoints=[{
                'compound_id': 'BPR_3M03FN01',
                'x_value': 100.0, 'x_type': 'concentration',
                'replicate': 'Mean', 'value': 0.25,
                'is_control': False, 'readout_type': 'mRNA_remaining',
                'raw_cp': None,
            }],
            summaries=[{'compound_id': 'BPR_3M03FN01',
                        'max_kd_pct': 75.0, 'ic50_nm': 5.0, 'rank': 1}],
            mock_values={},
        )

    def test_transfection_metadata_in_preview(self):
        tf = ParsedTransfectionFile(
            cell_line='Hepa1-6',
            notes='Duration: 24h; Primer: FASN/GAPDH',
            mapping={'siRNA-01': 'BPR_3M03FN01'},
        )
        preview = build_preview(
            None, self._make_summary(), [],
            'batch-X', 'FASN mRNA',
            transfection_parsed=tf,
        )
        self.assertEqual(preview['cell_line'], 'Hepa1-6')
        self.assertEqual(preview['notes'], 'Duration: 24h; Primer: FASN/GAPDH')

    def test_no_transfection_preview_has_empty_strings(self):
        preview = build_preview(
            None, self._make_summary(), [],
            'batch-X', 'FASN mRNA',
        )
        self.assertEqual(preview['cell_line'], '')
        self.assertEqual(preview['notes'], '')


class CpCoverageTest(TestCase):
    def _make_summary_with_two_compounds(self):
        dps = []
        for cid in ['BPR_3M03FN01', 'BPR_3M03FN02']:
            for dose in [100.0, 10.0]:
                for rep in ('A', 'B', 'Mean'):
                    dps.append({
                        'compound_id': cid, 'x_value': dose,
                        'x_type': 'concentration', 'replicate': rep,
                        'value': 0.5, 'is_control': False,
                        'readout_type': 'mRNA_remaining', 'raw_cp': None,
                    })
        return ParsedSummary(
            assay_name='FASN',
            mapping={'siRNA-01': 'BPR_3M03FN01', 'siRNA-02': 'BPR_3M03FN02'},
            datapoints=dps, summaries=[], mock_values={},
        )

    def test_no_cp_files_all_false(self):
        preview = build_preview(None, self._make_summary_with_two_compounds(), [],
                                'b1', 'FASN')
        self.assertFalse(preview['cp_coverage']['BPR_3M03FN01'])
        self.assertFalse(preview['cp_coverage']['BPR_3M03FN02'])

    def test_cp_coverage_counted_correctly(self):
        from app01.upload_pipeline import ParsedCpFile
        # Simulate Cp data only for compound 01
        cp_data = {
            ('siRNA-01', 100.0): {'rep_A': {'GAPDH': {'A': 16.0}}, 'rep_B': {'GAPDH': {'A': 16.1}}},
            ('siRNA-01', 10.0):  {'rep_A': {'GAPDH': {'A': 16.2}}, 'rep_B': {'GAPDH': {'A': 16.3}}},
        }
        cp = ParsedCpFile(assay_name='FASN', reference_gene='GAPDH',
                          target_gene='FASN', cp_data=cp_data)
        preview = build_preview(None, self._make_summary_with_two_compounds(), [cp],
                                'b1', 'FASN')
        self.assertTrue(preview['cp_coverage']['BPR_3M03FN01'])
        self.assertFalse(preview['cp_coverage']['BPR_3M03FN02'])


from django.urls import reverse


class BatchListViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='admin1', password='pass123', user_type='admin'
        )
        self.client.login(username='admin1', password='pass123')
        compound = Compound.objects.create(compound_id='BPR_3M03FN01')
        exp = Experiment.objects.create(
            compound=compound, exp_type='in_vitro',
            assay_name='FASN mRNA', batch_label='batch-A',
        )
        DataPoint.objects.create(
            experiment=exp, x_value=100.0, x_type='concentration',
            replicate='Mean', value=0.25, readout_type='mRNA_remaining',
        )

    def test_list_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse('batch_list'))
        self.assertRedirects(r, '/login/?next=/batches/')

    def test_list_shows_batch(self):
        r = self.client.get(reverse('batch_list'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'batch-A')

    def test_list_shows_compound_count(self):
        r = self.client.get(reverse('batch_list'))
        self.assertContains(r, '1')  # 1 compound


class BatchDeleteViewTest(TestCase):
    def _make_data(self, batch_label='batch-del'):
        compound = Compound.objects.create(compound_id='BPR_3M03FN99')
        exp = Experiment.objects.create(
            compound=compound, exp_type='in_vitro',
            assay_name='FASN mRNA', batch_label=batch_label,
        )
        DataPoint.objects.create(
            experiment=exp, x_value=100.0, x_type='concentration',
            replicate='Mean', value=0.25, readout_type='mRNA_remaining',
        )
        return compound

    def test_guest_cannot_delete(self):
        LmsUser.objects.create_user(username='g1', password='pass', user_type='guest')
        self._make_data()
        self.client.login(username='g1', password='pass')
        r = self.client.post(reverse('batch_delete', args=['batch-del']))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Experiment.objects.filter(batch_label='batch-del').count(), 1)

    def test_data_admin_can_delete(self):
        LmsUser.objects.create_user(username='da1', password='pass', user_type='data_admin')
        compound = self._make_data()
        self.client.login(username='da1', password='pass')
        r = self.client.post(reverse('batch_delete', args=['batch-del']))
        self.assertRedirects(r, reverse('batch_list'))
        self.assertEqual(Experiment.objects.filter(batch_label='batch-del').count(), 0)
        # Compound must NOT be deleted
        self.assertTrue(Compound.objects.filter(compound_id='BPR_3M03FN99').exists())

    def test_datapoints_cascade_deleted(self):
        LmsUser.objects.create_user(username='da2', password='pass', user_type='data_admin')
        self._make_data()
        self.client.login(username='da2', password='pass')
        self.client.post(reverse('batch_delete', args=['batch-del']))
        self.assertEqual(DataPoint.objects.filter(
            experiment__batch_label='batch-del'
        ).count(), 0)


class InVivoModelTest(TestCase):
    def _make_experiment(self):
        compound, _ = Compound.objects.get_or_create(compound_id='350025087')
        return Experiment.objects.create(
            compound=compound,
            exp_type='in_vivo',
            assay_name='KD% time-course',
            batch_label='B20260615120000',
        )

    def test_experiment_has_animal_fields(self):
        exp = self._make_experiment()
        exp.animal_species = 'mouse'
        exp.animal_strain = 'C57BL/6'
        exp.route = 'SC'
        exp.gender = 'male'
        exp.time_unit = 'day'
        exp.dose_info = '3mpk Q2W*3'
        exp.save()
        exp.refresh_from_db()
        self.assertEqual(exp.animal_species, 'mouse')
        self.assertEqual(exp.time_unit, 'day')
        self.assertEqual(exp.dose_info, '3mpk Q2W*3')

    def test_experiment_animal_fields_blank_by_default(self):
        exp = self._make_experiment()
        exp.refresh_from_db()
        self.assertEqual(exp.animal_species, '')
        self.assertEqual(exp.time_unit, '')

    def test_body_weight_readout_choice_exists(self):
        choices = dict(DataPoint.READOUT_CHOICES)
        self.assertIn('body_weight', choices)

    def test_experiment_attachment_create(self):
        import tempfile, shutil
        from django.test import override_settings
        from app01.models import ExperimentAttachment
        from django.core.files.base import ContentFile
        tmp = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=tmp):
                exp = self._make_experiment()
                att = ExperimentAttachment.objects.create(
                    experiment=exp,
                    label='Raw data',
                )
                att.file.save('test.csv', ContentFile(b'a,b\n1,2'), save=True)
                att.refresh_from_db()
                self.assertTrue(att.file.name.endswith('test.csv'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


from app01.upload_pipeline import (
    ParsedInVivoFile, ParsedInVivoGroup, ParsedInVivoTimepoint,
    parse_invivo_kd_file,
)

INVIVO_KD_CSV = """\
,CompA ,CompA ,CompA ,CompB ,CompB ,CompB
-7,0,0,0,0,0,0
14,-95.67,-94.49,-95.24*,-80.1,-82.3,-81.5
28,-97.16,-96.57,-93.37*,-85.0,-87.2,-86.1
"""


class ParseInVivoKdFileTest(TestCase):
    def _parse(self, csv_text=INVIVO_KD_CSV):
        class F:
            def read(self_):
                return csv_text.encode('utf-8')
        return parse_invivo_kd_file(F())

    def test_readout_type(self):
        result = self._parse()
        self.assertEqual(result.readout_type, 'knockdown_pct')

    def test_needs_dose(self):
        result = self._parse()
        self.assertTrue(result.needs_dose)

    def test_groups_count(self):
        result = self._parse()
        self.assertEqual(len(result.groups), 2)

    def test_compound_ids(self):
        result = self._parse()
        ids = {g.compound_id for g in result.groups}
        self.assertIn('CompA', ids)
        self.assertIn('CompB', ids)

    def test_timepoints_correct(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        tp14 = next(tp for tp in comp_a.timepoints if tp.time == 14.0)
        self.assertAlmostEqual(tp14.mean, (-95.67 + -94.49 + -95.24) / 3, places=2)
        self.assertEqual(tp14.n, 3)

    def test_star_stripped(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        tp28 = next(tp for tp in comp_a.timepoints if tp.time == 28.0)
        self.assertAlmostEqual(tp28.mean, (-97.16 + -96.57 + -93.37) / 3, places=2)

    def test_time_unit_day_when_negatives(self):
        result = self._parse()
        self.assertEqual(result.inferred_time_unit, 'day')

    def test_time_unit_unknown_when_no_negatives(self):
        csv_text = ",CompA ,CompA ,CompA\n14,-95.67,-94.49,-95.24\n28,-97.16,-96.57,-93.37\n"
        result = self._parse(csv_text)
        self.assertEqual(result.inferred_time_unit, 'unknown')

    def test_empty_cells_skipped(self):
        csv_text = ",CompA ,CompA ,CompA\n14,-95.67,,-95.24\n"
        result = self._parse(csv_text)
        comp_a = result.groups[0]
        tp14 = comp_a.timepoints[0]
        self.assertEqual(tp14.n, 2)
        self.assertAlmostEqual(tp14.mean, (-95.67 + -95.24) / 2, places=2)

    def test_malformed_file_returns_empty(self):
        result = self._parse("garbage\nno data here\n")
        self.assertEqual(result.groups, [])


from app01.upload_pipeline import (
    parse_body_weight_file, detect_invivo_file_type,
)

BODY_WEIGHT_CSV = """\
,CompA 3mpk Q2W3,CompA 3mpk Q2W3,CompA 3mpk Q2W3,Saline QW5,Saline QW5,Saline QW5
0,45.2,46.1,44.8,45.0,46.3,44.9
7,44.8,45.0*,43.9,45.5,46.0,45.1
14,43.1,44.2,42.8*,45.2,45.8,45.0
"""


class ParseBodyWeightFileTest(TestCase):
    def _parse(self, csv_text=BODY_WEIGHT_CSV):
        class F:
            def read(self_):
                return csv_text.encode('utf-8')
        return parse_body_weight_file(F())

    def test_readout_type(self):
        result = self._parse()
        self.assertEqual(result.readout_type, 'body_weight')

    def test_needs_dose_false(self):
        result = self._parse()
        self.assertFalse(result.needs_dose)

    def test_groups_count(self):
        result = self._parse()
        self.assertEqual(len(result.groups), 2)

    def test_dose_info_extracted(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        self.assertEqual(comp_a.dose_info, '3mpk Q2W3')

    def test_saline_group(self):
        result = self._parse()
        saline = next(g for g in result.groups if g.compound_id == 'Saline')
        self.assertEqual(saline.dose_info, 'QW5')

    def test_timepoints_count(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        self.assertEqual(len(comp_a.timepoints), 3)

    def test_mean_computed(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        tp0 = next(tp for tp in comp_a.timepoints if tp.time == 0.0)
        self.assertAlmostEqual(tp0.mean, (45.2 + 46.1 + 44.8) / 3, places=4)

    def test_star_stripped(self):
        result = self._parse()
        comp_a = next(g for g in result.groups if g.compound_id == 'CompA')
        tp7 = next(tp for tp in comp_a.timepoints if tp.time == 7.0)
        self.assertAlmostEqual(tp7.mean, (44.8 + 45.0 + 43.9) / 3, places=4)

    def test_time_unit_unknown_positive_only(self):
        result = self._parse()
        self.assertEqual(result.inferred_time_unit, 'unknown')


class DetectInVivoFileTypeTest(TestCase):
    def _detect(self, csv_text):
        class F:
            def read(self_):
                return csv_text.encode('utf-8')
        return detect_invivo_file_type(F())

    def test_detects_body_weight(self):
        self.assertEqual(self._detect(BODY_WEIGHT_CSV), 'body_weight')

    def test_detects_kd(self):
        self.assertEqual(self._detect(INVIVO_KD_CSV), 'knockdown_pct')

    def test_unknown_on_garbage(self):
        self.assertEqual(self._detect("hello\nworld\n"), 'unknown')


import tempfile, os, shutil


class InVivoUploadViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='uploader', password='pass', user_type='data_admin'
        )
        self.client.login(username='uploader', password='pass')

    def _kd_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        content = b",CompA ,CompA ,CompA\n-7,0,0,0\n14,-95.0,-94.0,-93.0\n"
        return SimpleUploadedFile('data2.csv', content, content_type='text/csv')

    def _bw_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        content = b",CompA 3mpk SC,CompA 3mpk SC,CompA 3mpk SC\n0,45,46,44\n7,43,44,42\n"
        return SimpleUploadedFile('data3.csv', content, content_type='text/csv')

    def test_get_renders_form(self):
        r = self.client.get(reverse('invivo_upload'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'invivo_file')

    def test_get_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse('invivo_upload'))
        self.assertRedirects(r, '/login/?next=/upload/invivo/')

    def test_post_without_file_shows_error(self):
        r = self.client.post(reverse('invivo_upload'), {'project_code': '3M03'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '请上传')

    def test_post_without_project_code_shows_error(self):
        r = self.client.post(reverse('invivo_upload'), {'invivo_file': self._kd_file()})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '项目号')

    def test_post_kd_file_stores_preview_in_session(self):
        r = self.client.post(reverse('invivo_upload'), {
            'project_code': '3M03',
            'invivo_file': self._kd_file(),
        })
        self.assertRedirects(r, '/upload/invivo/?preview=1')
        self.assertIn('invivo_preview', self.client.session)
        preview = self.client.session['invivo_preview']
        self.assertEqual(preview['readout_type'], 'knockdown_pct')
        self.assertTrue(preview['needs_dose'])

    def test_confirm_writes_experiments(self):
        # Step 1: upload
        self.client.post(reverse('invivo_upload'), {
            'project_code': '3M03',
            'invivo_file': self._kd_file(),
        })
        # Step 2: confirm
        r = self.client.post(reverse('invivo_upload_confirm'), {
            'time_unit': 'day',
            'dose_override': '10mpk SC',
            'animal_species': 'mouse',
            'animal_strain': 'C57BL/6',
            'route': 'SC',
            'gender': 'male',
        })
        self.assertRedirects(r, reverse('invivo_upload'))
        self.assertEqual(Experiment.objects.filter(exp_type='in_vivo').count(), 1)
        exp = Experiment.objects.get(exp_type='in_vivo')
        self.assertEqual(exp.animal_species, 'mouse')
        self.assertEqual(exp.time_unit, 'day')
        self.assertEqual(exp.dose_info, '10mpk SC')
        # DataPoints: day -7 (Mean=0, SD=0) + day 14 (Mean, SD) = 4 DataPoints
        self.assertEqual(DataPoint.objects.filter(experiment=exp).count(), 4)

    def test_confirm_missing_fields_rerenders(self):
        self.client.post(reverse('invivo_upload'), {
            'project_code': '3M03',
            'invivo_file': self._kd_file(),
        })
        r = self.client.post(reverse('invivo_upload_confirm'), {
            'time_unit': 'day',
            # missing dose_override, animal_species, etc.
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '请填写')

    def test_confirm_creates_compound_if_missing(self):
        self.client.post(reverse('invivo_upload'), {
            'project_code': '3M03',
            'invivo_file': self._kd_file(),
        })
        self.client.post(reverse('invivo_upload_confirm'), {
            'time_unit': 'day', 'dose_override': '10mpk',
            'animal_species': 'mouse', 'animal_strain': 'C57BL/6',
            'route': 'SC', 'gender': 'male',
        })
        self.assertTrue(Compound.objects.filter(compound_id='CompA').exists())


from unittest.mock import patch, MagicMock  # used by DetectFileLLMTest, SmartUploadViewTest
from django.test import override_settings  # used by DetectFileLLMTest, SmartUploadConfirmTest
from django.core.files.uploadedfile import SimpleUploadedFile  # used by all smart-upload tests
from django.urls import reverse  # used by SmartUploadViewTest, SmartUploadConfirmTest

from app01.upload_pipeline import (
    detect_file_type_rules,  # detect_file_type_llm added in Task 2
    detect_file_type_llm,
)


class DetectFileTypeRulesTest(TestCase):
    def _f(self, content: str):
        return SimpleUploadedFile('test.csv', content.encode('utf-8'))

    def test_vitro_summary_ic50_header(self):
        f = self._f('compound_id,IC50 (nM),Max KD\nBPR_3M03FN01,1.5,0.8\n')
        self.assertEqual(detect_file_type_rules(f), 'vitro_summary')

    def test_vitro_summary_max_kd_header(self):
        f = self._f('compound_id,MaxKD (%)\nBPR_3M03FN01,0.8\n')
        self.assertEqual(detect_file_type_rules(f), 'vitro_summary')

    def test_vitro_transfection_sirna_header(self):
        f = self._f('siRNA,compound_id,cell_line\nsiRNA-01,BPR_3M03FN01,HepG2\n')
        self.assertEqual(detect_file_type_rules(f), 'vitro_transfection')

    def test_vitro_seq_modify_seq_header(self):
        f = self._f('compound_id,modify_seq\nBPR_3M03FN01,mAmGfUmA\n')
        self.assertEqual(detect_file_type_rules(f), 'vitro_seq')

    def test_invivo_kd_delegation(self):
        content = 'CompA,CompA,CompA\n-7,0.0,0.1,-0.1\n14,-30.5,-31.2,-29.8\n'
        f = self._f(content)
        self.assertEqual(detect_file_type_rules(f), 'invivo_kd')

    def test_vitro_seq_sirnaid_header(self):
        # Production sequence file format: siRNAID column must not be mistaken for transfection
        f = self._f('siRNAID,SS,AS\nBPR_3M03FN01,mAmGfUmA,mUmCfGmA\n')
        self.assertEqual(detect_file_type_rules(f), 'vitro_seq')

    def test_unknown_on_garbage(self):
        f = self._f('col1,col2,col3\nfoo,bar,baz\n')
        self.assertEqual(detect_file_type_rules(f), 'unknown')


import json as _json_mod


class DetectFileLLMTest(TestCase):
    def _f(self, content: str = 'col1,col2\nfoo,bar\n'):
        return SimpleUploadedFile('mystery.csv', content.encode('utf-8'))

    def _mock_response(self, label: str):
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json_mod.dumps(
            {'choices': [{'message': {'content': label}}]}
        ).encode('utf-8')
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @override_settings(
        DEEPSEEK_API_KEY='sk-test',
        DEEPSEEK_API_URL='https://api.deepseek.com/chat/completions',
        DEEPSEEK_MODEL='deepseek-chat',
    )
    def test_calls_api_returns_label(self):
        with patch('app01.upload_pipeline.urllib.request.urlopen', return_value=self._mock_response('vitro_summary')):
            result = detect_file_type_llm('mystery.csv', self._f())
        self.assertEqual(result, 'vitro_summary')

    @override_settings(
        DEEPSEEK_API_KEY='sk-test',
        DEEPSEEK_API_URL='https://api.deepseek.com/chat/completions',
        DEEPSEEK_MODEL='deepseek-chat',
    )
    def test_api_failure_returns_unknown(self):
        with patch('app01.upload_pipeline.urllib.request.urlopen', side_effect=Exception('network error')):
            result = detect_file_type_llm('mystery.csv', self._f())
        self.assertEqual(result, 'unknown')

    @override_settings(
        DEEPSEEK_API_KEY='',
        DEEPSEEK_API_URL='https://api.deepseek.com/chat/completions',
        DEEPSEEK_MODEL='deepseek-chat',
    )
    def test_no_api_key_skips_call(self):
        with patch('app01.upload_pipeline.urllib.request.urlopen') as mock_urlopen:
            result = detect_file_type_llm('mystery.csv', self._f())
        mock_urlopen.assert_not_called()
        self.assertEqual(result, 'unknown')


class SmartUploadViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(username='smarttester', password='pw')
        self.client.force_login(self.user)

    def _kd_csv(self):
        content = b'CompA,CompA,CompA\n-7,0.0,0.1,-0.1\n14,-30.5,-31.2,-29.8\n'
        return SimpleUploadedFile('data2.csv', content, content_type='text/csv')

    def _summary_csv(self):
        content = b'compound_id,IC50 (nM),Max KD (%)\nBPR_3M03FN01,1.5,0.8\n'
        return SimpleUploadedFile('summary.csv', content, content_type='text/csv')

    def test_get_200(self):
        r = self.client.get(reverse('smart_upload'))
        self.assertEqual(r.status_code, 200)

    def test_login_required(self):
        self.client.logout()
        r = self.client.get(reverse('smart_upload'))
        self.assertRedirects(r, '/login/?next=/upload/smart/')

    def test_post_no_files_shows_error(self):
        r = self.client.post(reverse('smart_upload'), {'project_code': '3M03'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '请至少')

    def test_post_invivo_kd_file_creates_invivo_groups(self):
        r = self.client.post(reverse('smart_upload'), {
            'project_code': '3M03',
            'files': self._kd_csv(),
        })
        self.assertRedirects(r, '/upload/smart/?preview=1')
        preview = self.client.session['smart_preview']
        self.assertEqual(len(preview['invivo_groups']), 1)
        self.assertEqual(preview['invivo_groups'][0]['readout_type'], 'knockdown_pct')
        self.assertIsNone(preview['invitro'])

    def test_post_vitro_file_detected_as_summary(self):
        r = self.client.post(reverse('smart_upload'), {
            'project_code': '3M03',
            'files': self._summary_csv(),
        })
        self.assertRedirects(r, '/upload/smart/?preview=1')
        preview = self.client.session['smart_preview']
        self.assertEqual(preview['file_detections'][0]['detected_type'], 'vitro_summary')
        self.assertEqual(preview['file_detections'][0]['confidence'], 'rule')

    def test_get_preview_renders_phase2(self):
        self.client.post(reverse('smart_upload'), {
            'project_code': '3M03',
            'files': self._kd_csv(),
        })
        r = self.client.get(reverse('smart_upload') + '?preview=1')
        self.assertEqual(r.status_code, 200)


class SmartUploadConfirmTest(TestCase):
    def setUp(self):
        self.tmp_media = tempfile.mkdtemp()
        self.user = LmsUser.objects.create_user(username='confirmtester', password='pw')
        self.client.force_login(self.user)

    def tearDown(self):
        shutil.rmtree(self.tmp_media, ignore_errors=True)

    def _upload_kd(self):
        """POST a KD file to smart_upload to populate the session."""
        kd_csv = b'CompA,CompA,CompA\n-7,0.0,0.1,-0.1\n14,-30.5,-31.2,-29.8\n'
        f = SimpleUploadedFile('data2.csv', kd_csv, content_type='text/csv')
        with override_settings(MEDIA_ROOT=self.tmp_media):
            self.client.post(reverse('smart_upload'), {'project_code': '3M03', 'files': f})

    def _confirm_post(self, extra=None):
        data = {
            'time_unit_0': 'day',
            'dose_override_0': '10mpk SC',
            'animal_species_0': 'mouse',
            'animal_strain_0': 'C57BL/6',
            'route_0': 'SC',
            'gender_0': 'male',
        }
        if extra:
            data.update(extra)
        with override_settings(MEDIA_ROOT=self.tmp_media):
            return self.client.post(reverse('smart_upload_confirm'), data)

    def test_missing_time_unit_returns_error(self):
        self._upload_kd()
        r = self._confirm_post(extra={'time_unit_0': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '时间单位')

    def test_missing_animal_species_returns_error(self):
        self._upload_kd()
        r = self._confirm_post(extra={'animal_species_0': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '物种')

    def test_successful_invivo_confirm_writes_experiments(self):
        with override_settings(MEDIA_ROOT=self.tmp_media):
            self._upload_kd()
            r = self._confirm_post()
        self.assertRedirects(r, reverse('smart_upload'))
        self.assertEqual(Experiment.objects.filter(exp_type='in_vivo').count(), 1)
        exp = Experiment.objects.get(exp_type='in_vivo')
        self.assertEqual(exp.animal_species, 'mouse')
        self.assertEqual(exp.time_unit, 'day')
        self.assertEqual(DataPoint.objects.filter(experiment=exp).count(), 4)

    def test_session_cleared_after_confirm(self):
        with override_settings(MEDIA_ROOT=self.tmp_media):
            self._upload_kd()
            self._confirm_post()
        self.assertNotIn('smart_preview', self.client.session)


# ---- BuildVitroRowsTest ----
class BuildVitroRowsTest(TestCase):
    def _make_exp(self):
        c = Compound.objects.create(compound_id='BPR_VTTEST01')
        return Experiment.objects.create(
            compound=c, exp_type='in_vitro', assay_name='test', batch_label='BV1'
        )

    def test_sorted_high_to_low(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=1.0, x_type='concentration', replicate='Mean', value=0.87, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=10.0, x_type='concentration', replicate='Mean', value=0.50, readout_type='mRNA_remaining')
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual([r['dose'] for r in rows], [100.0, 10.0, 1.0])

    def test_only_mean_replicate(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='A', value=0.20, readout_type='mRNA_remaining')
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='B', value=0.30, readout_type='mRNA_remaining')
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['mean'], 0.25)

    def test_skip_control(self):
        from app01.views import _build_vitro_rows
        exp = self._make_exp()
        DataPoint.objects.create(experiment=exp, x_value=0.0, x_type='concentration', replicate='Mean', value=1.01, readout_type='mRNA_remaining', is_control=True)
        DataPoint.objects.create(experiment=exp, x_value=100.0, x_type='concentration', replicate='Mean', value=0.25, readout_type='mRNA_remaining', is_control=False)
        rows = _build_vitro_rows(list(exp.datapoints.all()))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['dose'], 100.0)


# ---- BuildInvivoRowsTest ----
class BuildInvivoRowsTest(TestCase):
    def _make_exp(self, time_unit='day'):
        from app01.models import Compound, Experiment
        c = Compound.objects.create(compound_id='BPR_IVTEST01')
        return Experiment.objects.create(
            compound=c, exp_type='in_vivo', assay_name='test',
            batch_label='BI1', time_unit=time_unit
        )

    def test_day_unit_filters_multiples_of_7(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        for day, val in [(0.0, 0.0), (3.0, -10.0), (7.0, -30.0), (14.0, -95.0), (10.0, -50.0)]:
            DataPoint.objects.create(experiment=exp, x_value=day, x_type='timepoint', replicate='1', value=val, readout_type='knockdown_pct')
            DataPoint.objects.create(experiment=exp, x_value=day, x_type='timepoint', replicate='2', value=val - 2, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        labels = [r['label'] for r in rows]
        self.assertIn('Day 0', labels)
        self.assertIn('Day 7', labels)
        self.assertIn('Day 14', labels)
        self.assertNotIn('Day 3', labels)
        self.assertNotIn('Day 10', labels)

    def test_week_unit_shows_all(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('week')
        for wk in [1.0, 2.0, 3.0]:
            DataPoint.objects.create(experiment=exp, x_value=wk, x_type='timepoint', replicate='1', value=-80.0, readout_type='knockdown_pct')
            DataPoint.objects.create(experiment=exp, x_value=wk, x_type='timepoint', replicate='2', value=-82.0, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'week')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['label'], 'Week 1')

    def test_cv_calculation(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        # 3 replicates at day 7: -90, -92, -88  → mean=-90, sd≈2.0, cv≈2.22%
        for rep, val in [('1', -90.0), ('2', -92.0), ('3', -88.0)]:
            DataPoint.objects.create(experiment=exp, x_value=7.0, x_type='timepoint', replicate=rep, value=val, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['mean'], -90.0, places=1)
        self.assertIsNotNone(rows[0]['sd'])
        self.assertIsNotNone(rows[0]['cv'])
        self.assertGreater(rows[0]['cv'], 0)

    def test_mean_zero_cv_is_none(self):
        from app01.views import _build_invivo_rows
        exp = self._make_exp('day')
        for rep in ['1', '2']:
            DataPoint.objects.create(experiment=exp, x_value=0.0, x_type='timepoint', replicate=rep, value=0.0, readout_type='knockdown_pct')
        rows = _build_invivo_rows(list(exp.datapoints.all()), 'day')
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['cv'])


# ---- AttachmentDownloadTest ----
class AttachmentDownloadTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='dltest', password='pass', user_type='admin'
        )
        self.client.login(username='dltest', password='pass')
        c = Compound.objects.create(compound_id='BPR_ATTEST01')
        exp = Experiment.objects.create(
            compound=c, exp_type='in_vitro', assay_name='test', batch_label='AT1'
        )
        # Create attachment with an in-memory file
        from django.core.files.base import ContentFile
        self.att = ExperimentAttachment(experiment=exp, label='test_file.csv')
        self.att.file.save('test_file.csv', ContentFile(b'col1,col2\n1,2\n'), save=True)

    def tearDown(self):
        if self.att.file:
            self.att.file.delete(save=False)

    def test_valid_pk_returns_file(self):
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_invalid_pk_returns_404(self):
        resp = self.client.get('/attachments/99999/download/')
        self.assertEqual(resp.status_code, 404)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(f'/attachments/{self.att.pk}/download/')
        self.assertEqual(resp.status_code, 302)
