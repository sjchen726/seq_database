import pandas as pd
from django.test import TestCase
from app01.models import Sequence, SeqModule, DeliveryModule
from app01.views import normalize_middle_brackets, run_preflight_check, group_sequences, auto_register_bare_sequences
from app01.models import DuplexRelationship, SeqInfo


class NormalizeMiddleBracketsTests(TestCase):

    def test_no_brackets_unchanged(self):
        seq = "AmUmGmCmAmUmGm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_only_delivery5_unchanged(self):
        seq = "[invAb]AmUmGmCmAmUmGm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_only_delivery3_unchanged(self):
        seq = "AmUmGmCmAmUmGm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_delivery5_and_3_unchanged(self):
        seq = "[invAb]AmUmGmCmAmUmGm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_middle_bracket_normalized(self):
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]"
        expected = "[invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_middle_bracket_no_delivery(self):
        # Only 1 bracket block → len(blocks) = 1 ≤ 2 → unchanged
        seq = "AmUmGm[LK1-L96-LK1]CmAmUm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_delivery5_and_middle_bracket(self):
        # 2 bracket blocks → len(blocks) = 2 ≤ 2 → unchanged (second block treated as delivery3)
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_three_brackets_middle_normalized(self):
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]"
        expected = "[invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_compound_delivery_preserved(self):
        seq = "[Vp-invAb]AmUmGm[LK1-L96-LK1]CmAmUm[invAb]"
        expected = "[Vp-invAb]AmUmGm-LK1-L96-LK1-CmAmUm[invAb]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_empty_string(self):
        self.assertEqual(normalize_middle_brackets(""), "")

    def test_multiple_middle_brackets(self):
        # 4 bracket blocks: first + 2 middle + last → both middle get normalized
        seq = "[d5]AAA[LK1]BBB[LK2]CCC[d3]"
        expected = "[d5]AAA-LK1-BBB-LK2-CCC[d3]"
        self.assertEqual(normalize_middle_brackets(seq), expected)


def _make_df(rows):
    """Helper: rows is list of dicts with Modify_seq, Seq_type, Project, Target, etc."""
    df = pd.DataFrame(rows)
    df = df.fillna('')
    df['__row_id'] = df.index
    df['__original_line'] = df.index + 2
    return df


class RunPreflightCheckTests(TestCase):

    def setUp(self):
        SeqModule.objects.get_or_create(keyword='Am', defaults={'base_char': 'A'})
        SeqModule.objects.get_or_create(keyword='Um', defaults={'base_char': 'U'})
        SeqModule.objects.get_or_create(keyword='Gm', defaults={'base_char': 'G'})
        SeqModule.objects.get_or_create(keyword='Cm', defaults={'base_char': 'C'})
        DeliveryModule.objects.get_or_create(keyword='invAb', defaults={'type_code': 'ligand'})
        DeliveryModule.objects.get_or_create(keyword='Vp', defaults={'type_code': 'ligand'})
        DeliveryModule.objects.get_or_create(keyword='LK1', defaults={'type_code': 'linker'})
        DeliveryModule.objects.get_or_create(keyword='L96', defaults={'type_code': 'linker'})

    def test_clean_pair_both_registered(self):
        """Both naked_seqs exist → auto_register_pairs is empty, clean_groups has the pair."""
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='SS')
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(result['auto_register_pairs'], [])
        self.assertEqual(result['unknown_module_pairs'], [])
        self.assertEqual(len(result['clean_groups']), 1)

    def test_unregistered_ss_added_to_auto_register(self):
        """SS naked_seq not in DB → pair added to auto_register_pairs."""
        Sequence.objects.create(seq='AUGCAUGCAU', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCmAmUm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['auto_register_pairs']), 1)
        pair = result['auto_register_pairs'][0]
        self.assertFalse(pair['ss_exists'])
        self.assertTrue(pair['as_exists'])
        self.assertEqual(pair['naked_ss'], 'AUGCAUGCAU')

    def test_transcript_position_from_ss_row(self):
        """Transcript/Position taken from SS row when present."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': 'NM_001234', 'Position': '99',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': '', 'Position': '',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['auto_register_pairs']), 1)
        pair = result['auto_register_pairs'][0]
        self.assertEqual(pair['transcript'], 'NM_001234')
        self.assertEqual(pair['position'], '99')

    def test_transcript_falls_back_to_as_row(self):
        """Transcript taken from AS row when SS row is empty."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': '', 'Position': '',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Transcript': 'NM_999', 'Position': '42',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['auto_register_pairs']), 1)
        pair = result['auto_register_pairs'][0]
        self.assertEqual(pair['transcript'], 'NM_999')
        self.assertEqual(pair['position'], '42')

    def test_unknown_seqmodule_token_skips_pair(self):
        """Unknown SeqModule token → pair moves to unknown_module_pairs, not clean_groups."""
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': 'AmUmZmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['unknown_module_pairs']), 1)
        self.assertEqual(len(result['clean_groups']), 0)
        self.assertIn('Z', result['unknown_module_pairs'][0]['unknown_tokens'])

    def test_unknown_delivery_token_warns_only(self):
        """Unknown DeliveryModule token → warning only, pair still in clean_groups."""
        Sequence.objects.create(seq='AUGCAUGC', seq_type='SS')
        Sequence.objects.create(seq='AUGCAUGC', seq_type='AS')
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': '[UNKNOWN]AmUmGmCmAmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': 'AmUmGmCmAmUmGmCm', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['unknown_module_pairs']), 0)
        self.assertEqual(len(result['unknown_delivery_warnings']), 1)
        self.assertIn('UNKNOWN', result['unknown_delivery_warnings'][0]['unknown_tokens'])

    def test_dual_segment_linker_no_false_unknown(self):
        """Dual-segment sequence with -LK1-L96-LK1- linker is NOT flagged as unknown module."""
        # normalize_middle_brackets has already run before run_preflight_check,
        # so [LK1-L96-LK1] becomes -LK1-L96-LK1- in clean_seq.
        # Digits from linker names should NOT be flagged as unknown tokens.
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS',
             'Modify_seq': '[invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS',
             'Modify_seq': '[Vp]AmUmGmCmAmUm[invAb]',
             'Strand_MWs': '', 'Parents': '', 'Remarks': ''},
        ]
        df = _make_df(rows)
        ss_groups, _ = group_sequences(df)
        result = run_preflight_check(df, ss_groups)
        self.assertEqual(len(result['unknown_module_pairs']), 0,
                         f"Unexpected unknown tokens: {result['unknown_module_pairs']}")


class AutoRegisterTests(TestCase):

    def setUp(self):
        self.username = 'testuser'

    def _make_pair(self, naked_ss, naked_as, ss_exists=False, as_exists=False,
                   transcript='', position='', project='P1'):
        return {
            'ss_row_id': 0,
            'as_row_id': 1,
            'naked_ss': naked_ss,
            'naked_as': naked_as,
            'ss_exists': ss_exists,
            'as_exists': as_exists,
            'transcript': transcript,
            'position': position,
            'project': project,
        }

    def test_both_missing_creates_all(self):
        """Both SS and AS missing → creates SS, AS, duplex, DuplexRelationship, SeqInfo."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG')]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        self.assertTrue(Sequence.objects.filter(seq='AUGCAU', seq_type='SS').exists())
        self.assertTrue(Sequence.objects.filter(seq='UGCAUG', seq_type='AS').exists())
        self.assertTrue(Sequence.objects.filter(seq='UGCAUG, AUGCAU', seq_type='duplex').exists())
        ss_obj = Sequence.objects.get(seq='AUGCAU', seq_type='SS')
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        self.assertTrue(DuplexRelationship.objects.filter(ss_seq=ss_obj, as_seq=as_obj).exists())
        self.assertTrue(SeqInfo.objects.filter(sequence=ss_obj).exists())

    def test_ss_missing_as_exists(self):
        """SS missing, AS exists → creates SS + new duplex + DuplexRelationship."""
        as_obj = Sequence.objects.create(seq='UGCAUG', seq_type='AS')
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', ss_exists=False, as_exists=True)]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        self.assertTrue(Sequence.objects.filter(seq='AUGCAU', seq_type='SS').exists())
        ss_obj = Sequence.objects.get(seq='AUGCAU', seq_type='SS')
        self.assertTrue(DuplexRelationship.objects.filter(ss_seq=ss_obj, as_seq=as_obj).exists())

    def test_both_exist_skips_registration(self):
        """Both SS and AS exist → no new SS/AS created, duplex relationship still ensured."""
        Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        Sequence.objects.create(seq='UGCAUG', seq_type='AS')
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', ss_exists=True, as_exists=True)]
        registered_log, skipped_log = auto_register_bare_sequences(pairs, self.username)
        self.assertEqual(skipped_log, [])
        self.assertEqual(Sequence.objects.filter(seq_type='SS').count(), 1)
        self.assertEqual(Sequence.objects.filter(seq_type='AS').count(), 1)

    def test_transcript_and_position_saved_in_seqinfo(self):
        """Transcript and Position stored in SeqInfo for SS."""
        pairs = [self._make_pair('AAAA', 'UUUU', transcript='NM_001', position='42')]
        auto_register_bare_sequences(pairs, self.username)
        ss_obj = Sequence.objects.get(seq='AAAA', seq_type='SS')
        info = SeqInfo.objects.get(sequence=ss_obj)
        self.assertEqual(info.Transcript, 'NM_001')
        self.assertEqual(info.Pos, '42')

    def test_one_pair_failure_does_not_rollback_others(self):
        """A failure in one pair does not prevent other pairs from registering."""
        good_pair = self._make_pair('CCCCCC', 'GGGGGG')
        # Force failure: naked_ss=None causes IntegrityError on create
        bad_pair = {**self._make_pair('', 'TTTTTT'), 'naked_ss': None}
        registered_log, skipped_log = auto_register_bare_sequences(
            [bad_pair, good_pair], self.username
        )
        self.assertTrue(Sequence.objects.filter(seq='CCCCCC', seq_type='SS').exists())
        self.assertEqual(len(skipped_log), 1)
