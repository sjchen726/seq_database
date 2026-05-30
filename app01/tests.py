import json
import pandas as pd
from django.test import TestCase
from app01.models import Sequence, SeqModule, DeliveryModule, Delivery, DeliveryProject, LmsUser
from app01.views import (
    normalize_middle_brackets, run_preflight_check, group_sequences,
    auto_register_bare_sequences, check_duplicates,
    build_combo_re, normalize_tmp_seq_with_combo,
)
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
        # Verify DuplexRelationship was created even when both strands pre-existed
        ss_obj = Sequence.objects.get(seq='AUGCAU', seq_type='SS')
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        self.assertTrue(
            DuplexRelationship.objects.filter(ss_seq=ss_obj, as_seq=as_obj).exists(),
            "DuplexRelationship must be created even when both strands pre-exist"
        )

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

    def test_as_chain_seqinfo_created(self):
        """auto_register_bare_sequences must create SeqInfo for AS chain too."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', transcript='NM_001', position='42')]
        auto_register_bare_sequences(pairs, self.username)
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        self.assertTrue(
            SeqInfo.objects.filter(sequence=as_obj).exists(),
            "SeqInfo must be created for AS chain"
        )

    def test_as_chain_seqinfo_has_correct_fields(self):
        """SeqInfo for AS chain should carry the same transcript/position as SS."""
        pairs = [self._make_pair('AUGCAU', 'UGCAUG', transcript='NM_999', position='77')]
        auto_register_bare_sequences(pairs, self.username)
        as_obj = Sequence.objects.get(seq='UGCAUG', seq_type='AS')
        info = SeqInfo.objects.get(sequence=as_obj)
        self.assertEqual(info.Transcript, 'NM_999')
        self.assertEqual(info.Pos, '77')


class CheckDuplicatesTests(TestCase):
    """Tests for check_duplicates() cross-project and same-project detection."""

    def setUp(self):
        # Minimal SeqModule entries so extract_naked_seq works (Am→A, Um→U, Gm→G, Cm→C)
        for kw, base in [('Am', 'A'), ('Um', 'U'), ('Gm', 'G'), ('Cm', 'C')]:
            SeqModule.objects.get_or_create(keyword=kw, defaults={'base_char': base, 'linker_connector': 'o'})

        # Register SS and AS bare sequences
        self.ss_seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.as_seq = Sequence.objects.create(seq='AUGCAU', seq_type='AS')

        # Create a Delivery in project BPR-350
        self.delivery_ss = Delivery.objects.create(
            sequence=self.ss_seq,
            duplex_id='BP000001',
            seq_type='SS',
            delivery5='invAb',
            delivery3='Vp',
            modify_seq='AmUmGmCmAmUm',
            linker_seq='AoUoGoCoAoU',
            project='BPR-350',
        )
        self.delivery_as = Delivery.objects.create(
            sequence=self.as_seq,
            duplex_id='BP000001',
            seq_type='AS',
            delivery5='Vp',
            delivery3='invAb',
            modify_seq='AmUmGmCmAmUm',
            linker_seq='AoUoGoCoAoU',
            project='BPR-350',
        )
        # DeliveryProject entries are auto-created by post_save signal on Delivery

    def _make_df(self, project, ss_seq, as_seq):
        """Build a minimal upload DataFrame for one SS+AS pair."""
        rows = [
            {
                'Project': project,
                'Seq_type': 'SS',
                'Modify_seq': f'[invAb]{ss_seq}[Vp]',
                '__row_id': 0,
                '__original_line': 2,
            },
            {
                'Project': project,
                'Seq_type': 'AS',
                'Modify_seq': f'[Vp]{as_seq}[invAb]',
                '__row_id': 1,
                '__original_line': 3,
            },
        ]
        df = pd.DataFrame(rows)
        df.index = df['__row_id'].astype(int)
        return df

    def _make_ss_groups(self, df):
        """Pair rows 0+1 as one SS+AS group."""
        return [(None, df.iloc[0]['Project'], [0, 1])]

    def test_same_project_duplicate_goes_to_repeated_ids(self):
        """Uploading same (naked_seq, d5, d3) to same project → repeated_ids, not cross."""
        df = self._make_df('BPR-350', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-350')
        self.assertIn(0, repeated_ids)
        self.assertIn(1, repeated_ids)
        self.assertEqual(cross, [])
        self.assertTrue(len(duplicate_meg) > 0)

    def test_cross_project_duplicate_triggers_share_list(self):
        """Uploading same (naked_seq, d5, d3) to different project → cross_project_duplicates."""
        df = self._make_df('BPR-3T03', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(repeated_ids, set())
        self.assertEqual(duplicate_meg, [])
        self.assertEqual(len(cross), 1)
        self.assertEqual(cross[0]['existing_duplex_id'], 'BP000001')
        self.assertEqual(cross[0]['target_project'], 'BPR-3T03')

    def test_new_sequence_not_in_db_no_duplicate(self):
        """A truly new (naked_seq, d5, d3) not in DB → nothing flagged."""
        df = self._make_df('BPR-3T03', 'AmGmCmUmAmUm', 'AmGmCmUmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(repeated_ids, set())
        self.assertEqual(duplicate_meg, [])
        self.assertEqual(cross, [])

    def test_linker_seq_format_difference_still_detected(self):
        """Even if stored linker_seq differs from computed, naked_seq match catches it."""
        # Modify the stored linker_seq to a deliberately different format
        self.delivery_ss.linker_seq = 'DIFFERENT_FORMAT'
        self.delivery_ss.save()
        self.delivery_as.linker_seq = 'DIFFERENT_FORMAT'
        self.delivery_as.save()
        # Should still detect cross-project via naked_seq
        df = self._make_df('BPR-3T03', 'AmUmGmCmAmUm', 'AmUmGmCmAmUm')
        ss_groups = self._make_ss_groups(df)
        repeated_ids, duplicate_meg, cross = check_duplicates(df, ss_groups, target_project='BPR-3T03')
        self.assertEqual(len(cross), 1, "Should detect cross-project even with mismatched linker_seq")


class DropAuthorSecurityTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='admin_test', password='pass', user_type='admin', is_admin=True
        )
        self.victim = LmsUser.objects.create_user(
            username='victim_user', password='pass', user_type='guest'
        )
        self.client.login(username='admin_test', password='pass')

    def test_get_request_returns_400(self):
        """GET to drop_author must be rejected (CSRF protection)."""
        response = self.client.get(f'/drop_author/?id={self.victim.id}')
        self.assertEqual(response.status_code, 405)
        self.assertTrue(LmsUser.objects.filter(id=self.victim.id).exists())

    def test_post_request_deletes_user(self):
        """POST to drop_author with valid id deletes the user."""
        response = self.client.post('/drop_author/', {'id': self.victim.id})
        self.assertIn(response.status_code, [200, 302])
        self.assertFalse(LmsUser.objects.filter(id=self.victim.id).exists())


class DownloadSelectedPermissionTests(TestCase):
    def setUp(self):
        # Create two sequences in different projects
        self.seq_a = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.seq_b = Sequence.objects.create(seq='UGCAUG', seq_type='SS')

        # Delivery in project "PROJ-A" (user has access)
        self.del_a = Delivery.objects.create(
            sequence=self.seq_a, duplex_id='BP000001',
            project='PROJ-A', seq_type='SS',
            delivery5='', delivery3='', modify_seq='AmUm', linker_seq='AoU',
        )
        # Delivery in project "PROJ-B" (user has NO access)
        self.del_b = Delivery.objects.create(
            sequence=self.seq_b, duplex_id='BP000002',
            project='PROJ-B', seq_type='SS',
            delivery5='', delivery3='', modify_seq='GmCm', linker_seq='GoC',
        )

        # User with access only to PROJ-A
        self.user = LmsUser.objects.create_user(
            username='proj_user', password='pass',
            user_type='delivery',
            permissions_project='PROJ-A',
        )
        self.client.login(username='proj_user', password='pass')

    def test_restricted_delivery_filtered_out(self):
        """User requesting BP000002 (PROJ-B) should receive 404 (not found)."""
        response = self.client.post(
            '/download_selected/',
            {
                'selected_ids': json.dumps(['BP000002']),
                'selected_columns': json.dumps(['duplex_id', 'project']),
            }
        )
        # User has no access to PROJ-B, so the delivery should be filtered out
        # and the view should return 404
        self.assertEqual(response.status_code, 404)

    def test_permitted_delivery_included(self):
        """User requesting BP000001 (PROJ-A) should receive the data row."""
        response = self.client.post(
            '/download_selected/',
            {
                'selected_ids': json.dumps(['BP000001']),
                'selected_columns': json.dumps(['duplex_id', 'project']),
            }
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        self.assertIn('BP000001', content)


class EditRegSeqProjectTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='admin2', password='pass', user_type='admin', is_admin=True
        )
        self.client.login(username='admin2', password='pass')
        self.seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.seqinfo = SeqInfo.objects.create(
            sequence=self.seq,
            project='OLD-PROJECT',
            Pos='1',
            Transcript='NM_001',
            Remark='',
        )

    def test_edit_project_is_saved(self):
        """Submitting a new project value must persist to SeqInfo.project."""
        response = self.client.post(
            f'/edit_reg_seq/?id={self.seq.rm_code}',
            {
                'edit_project': 'NEW-PROJECT',
                'edit_position': '1',
                'edit_Transcript': 'NM_001',
                'edit_Remark': '',
                'edit_date': '',
            }
        )
        self.seqinfo.refresh_from_db()
        self.assertEqual(
            self.seqinfo.project, 'NEW-PROJECT',
            f"Expected 'NEW-PROJECT', got '{self.seqinfo.project}'"
        )


class ASReversalTests(TestCase):
    def setUp(self):
        # Minimal DeliveryModule entries for the coloring function to work
        DeliveryModule.objects.get_or_create(keyword='Am', defaults={'type_code': 'mod'})
        DeliveryModule.objects.get_or_create(keyword='Um', defaults={'type_code': 'mod'})

    def test_as_strand_reversed_when_selected_is_ss(self):
        """AS strand must be reversed even when selected_seq_type='SS'."""
        from app01.views import get_delivery_colored
        tokens_as = get_delivery_colored('AmUm', selected_seq_type='SS', seq_type='AS')
        tokens_ss = get_delivery_colored('AmUm', selected_seq_type='SS', seq_type='SS')
        chars_as = [t['char'] for t in tokens_as if t['char'] not in ('s', 'o', '-')]
        chars_ss = [t['char'] for t in tokens_ss if t['char'] not in ('s', 'o', '-')]
        # AS should be reversed: Um then Am; SS should be forward: Am then Um
        self.assertEqual(chars_as, ['Um', 'Am'],
                         f"AS tokens not reversed: {chars_as}")
        self.assertEqual(chars_ss, ['Am', 'Um'],
                         f"SS tokens wrong order: {chars_ss}")

    def test_as_strand_reversed_when_selected_is_none(self):
        """AS strand must be reversed even when selected_seq_type is None."""
        from app01.views import get_delivery_colored
        tokens_as = get_delivery_colored('AmUm', selected_seq_type=None, seq_type='AS')
        chars_as = [t['char'] for t in tokens_as if t['char'] not in ('s', 'o', '-')]
        self.assertEqual(chars_as, ['Um', 'Am'],
                         f"AS tokens not reversed when selected=None: {chars_as}")

    def test_ss_strand_not_reversed(self):
        """SS strand must never be reversed regardless of selected_seq_type."""
        from app01.views import get_delivery_colored
        tokens = get_delivery_colored('AmUm', selected_seq_type='AS', seq_type='SS')
        chars = [t['char'] for t in tokens if t['char'] not in ('s', 'o', '-')]
        self.assertEqual(chars, ['Am', 'Um'],
                         f"SS tokens were incorrectly reversed: {chars}")


class AssignDuplexIdTests(TestCase):
    def _make_groups(self, n_groups):
        """Build n_groups ss_groups tuples: (project, target, [row_ids])."""
        groups = []
        for i in range(n_groups):
            groups.append((None, f'P{i}', [i * 2, i * 2 + 1]))
        return groups

    def _make_df(self, n_groups):
        import pandas as pd
        rows = []
        for i in range(n_groups * 2):
            rows.append({'__row_id': i, 'Seq_type': 'SS' if i % 2 == 0 else 'AS'})
        df = pd.DataFrame(rows)
        df.index = df['__row_id'].astype(int)
        return df

    def test_sequential_calls_generate_unique_ids(self):
        """Two calls must not generate overlapping IDs when IDs from the first are committed."""
        from app01.views import assign_duplex_ids
        Delivery.objects.create(
            sequence=Sequence.objects.create(seq='AAAA', seq_type='SS'),
            duplex_id='BP000001', project='P', seq_type='SS',
            delivery5='', delivery3='', modify_seq='Am', linker_seq='A',
        )
        df = self._make_df(2)
        groups = self._make_groups(2)

        # First call
        map1 = assign_duplex_ids(df, groups, set())

        # Simulate save_deliveries: commit the assigned IDs to DB
        for dup_id in set(map1.values()):
            seq = Sequence.objects.create(seq=f'SIMU{dup_id}', seq_type='SS')
            Delivery.objects.create(
                sequence=seq, duplex_id=dup_id, project='P', seq_type='SS',
                delivery5='', delivery3='', modify_seq='Am', linker_seq='A',
            )

        # Second call — must see the newly inserted IDs
        map2 = assign_duplex_ids(df, groups, set())
        ids1 = set(map1.values())
        ids2 = set(map2.values())
        self.assertTrue(ids1.isdisjoint(ids2),
                        f"Overlapping duplex IDs generated: {ids1 & ids2}")

    def test_id_format_is_bp_six_digits(self):
        """Generated IDs must match BP######."""
        import re
        from app01.views import assign_duplex_ids
        df = self._make_df(1)
        groups = self._make_groups(1)
        id_map = assign_duplex_ids(df, groups, set())
        for v in id_map.values():
            self.assertRegex(v, r'^BP\d{6}$')


class ModuleListPageParamTests(TestCase):
    def setUp(self):
        self.admin = LmsUser.objects.create_user(
            username='mod_admin', password='pass', user_type='admin',
            is_admin=True, is_superuser=True,
        )
        self.client.login(username='mod_admin', password='pass')
        self.module = DeliveryModule.objects.create(keyword='TestKW', type_code='test')

    def test_edit_module_redirect_preserves_page_and_q(self):
        """POST to edit_module should redirect to module_list with page and q params."""
        response = self.client.post(
            f'/edit_module/?id={self.module.id}',
            {
                'keyword': 'TestKW',
                'type_code': 'test',
                'Strand_MWs': '',
                'page': '3',
                'q': 'LP',
            }
        )
        self.assertRedirects(
            response, '/module_list/?page=3&q=LP',
            fetch_redirect_response=False,
        )

    def test_delete_module_redirect_preserves_page_and_q(self):
        """POST to delete_module should redirect to module_list with page and q params."""
        response = self.client.post(
            '/delete_module/',
            {'id': self.module.id, 'page': '2', 'q': 'C16'}
        )
        self.assertRedirects(
            response, '/module_list/?page=2&q=C16',
            fetch_redirect_response=False,
        )


class SaveDeliveriesTests(TestCase):
    def setUp(self):
        SeqModule.objects.get_or_create(keyword='Am', defaults={'base_char': 'A', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Um', defaults={'base_char': 'U', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Gm', defaults={'base_char': 'G', 'linker_connector': 'o'})
        SeqModule.objects.get_or_create(keyword='Cm', defaults={'base_char': 'C', 'linker_connector': 'o'})

        self.ss_seq = Sequence.objects.create(seq='AUGCAU', seq_type='SS')
        self.as_seq = Sequence.objects.create(seq='UGCAUG', seq_type='AS')

    def _make_df(self, rows):
        import pandas as pd
        df = pd.DataFrame(rows)
        df = df.fillna('')
        df['__row_id'] = df.index
        df['__original_line'] = df.index + 2
        return df

    def test_linker_seq_not_double_processed(self):
        """linker_seq in DB must equal add_o applied once, not twice."""
        from app01.views import add_o_to_all_rules_safe, save_deliveries, group_sequences, assign_duplex_ids
        modify_seq = 'AmUmGmCmAmUm'
        expected_linker = add_o_to_all_rules_safe(modify_seq)
        double_processed = add_o_to_all_rules_safe(expected_linker)
        if expected_linker == double_processed:
            self.skipTest("add_o is idempotent for this input")

        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS', 'Modify_seq': modify_seq,
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS', 'Modify_seq': modify_seq,
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
        ]
        df = self._make_df(rows)
        ss_groups, _ = group_sequences(df)
        duplex_id_map = assign_duplex_ids(df, ss_groups, set())
        save_deliveries(df, duplex_id_map, 'testuser')
        delivery = Delivery.objects.filter(sequence=self.ss_seq).first()
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.linker_seq, expected_linker,
                         f"Expected single-processed: {expected_linker!r}, got: {delivery.linker_seq!r}")

    def test_save_deliveries_creates_delivery_for_each_sequence(self):
        """save_deliveries must create deliveries for both SS and AS sequences in the upload."""
        from app01.views import save_deliveries, group_sequences, assign_duplex_ids
        rows = [
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'SS', 'Modify_seq': 'AmUmGmCmAmUm',
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
            {'Project': 'P1', 'Target': 'T', 'Seq_type': 'AS', 'Modify_seq': 'UmGmCmAmUmGm',
             'Strand_MWs': '', 'Parents': '', 'Remarks': '', 'Transcript': '', 'Position': ''},
        ]
        df = self._make_df(rows)
        ss_groups, _ = group_sequences(df)
        duplex_id_map = assign_duplex_ids(df, ss_groups, set())
        save_deliveries(df, duplex_id_map, 'testuser')

        # Both sequences must have a delivery
        self.assertTrue(Delivery.objects.filter(sequence=self.ss_seq).exists(),
                        "SS delivery was not created")
        self.assertTrue(Delivery.objects.filter(sequence=self.as_seq).exists(),
                        "AS delivery was not created")


class GroupSequencesOrderTests(TestCase):
    def _make_df(self, rows):
        df = pd.DataFrame(rows)
        df = df.fillna('')
        df['__row_id'] = df.index
        df['__original_line'] = df.index + 2
        return df

    def _row(self, seq_type, modify_seq='AmUm', project='P1'):
        return {'Seq_type': seq_type, 'Modify_seq': modify_seq, 'Project': project,
                'Target': 'T', 'Strand_MWs': '', 'Parents': '', 'Remarks': ''}

    def test_ss_then_as_pairs_correctly(self):
        """Classic order: SS row 0, AS row 1 → one group."""
        df = self._make_df([self._row('SS'), self._row('AS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 1)
        self.assertEqual(invalid, [])

    def test_as_then_ss_pairs_correctly(self):
        """Reversed order: AS row 0, SS row 1 → one group, SS id first in group."""
        df = self._make_df([self._row('AS'), self._row('SS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 1, f"Expected 1 group, got {len(ss_groups)}: {invalid}")
        self.assertEqual(invalid, [])
        _, _, group = ss_groups[0]
        ss_row_id = df[df['Seq_type'] == 'SS']['__row_id'].iloc[0]
        self.assertEqual(group[0], ss_row_id)

    def test_two_pairs_as_ss_ss_as(self):
        """AS,SS,SS,AS → two valid groups."""
        df = self._make_df([
            self._row('AS'), self._row('SS'),
            self._row('SS'), self._row('AS'),
        ])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 2)
        self.assertEqual(invalid, [])

    def test_unpaired_lone_ss_is_invalid(self):
        """SS with no adjacent AS → invalid."""
        df = self._make_df([self._row('SS')])
        ss_groups, invalid = group_sequences(df)
        self.assertEqual(len(ss_groups), 0)
        self.assertEqual(len(invalid), 1)


class RegSeqListPaginationTests(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='pager', password='pass', user_type='guest'
        )
        self.client.login(username='pager', password='pass')
        for i in range(25):
            seq = Sequence.objects.create(seq=f'AUGCAU{i:02d}', seq_type='SS')
            SeqInfo.objects.create(sequence=seq, project='P1', Pos='1', Remark='', Transcript='')

    def test_page_1_returns_correct_count(self):
        response = self.client.get('/reg_seq_list/?page=1&page_size=10')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['sequence_list']), 10)

    def test_page_2_returns_remaining(self):
        response = self.client.get('/reg_seq_list/?page=2&page_size=20')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['sequence_list']), 5)

    def test_page_obj_has_correct_count(self):
        response = self.client.get('/reg_seq_list/')
        self.assertEqual(response.context['page_obj'].paginator.count, 25)


class DefaultSeqTypeTests(TestCase):
    def test_default_is_ss_for_new_user(self):
        """New users default to 'SS' seq type."""
        from app01.views import get_user_default_seq_type
        user = LmsUser.objects.create_user(username='newuser', password='pass')
        self.assertEqual(get_user_default_seq_type(user), 'SS')

    def test_user_with_as_default_returns_as(self):
        """User with default_seq_type='AS' returns 'AS'."""
        from app01.views import get_user_default_seq_type
        user = LmsUser.objects.create_user(
            username='asuser', password='pass', default_seq_type='AS'
        )
        self.assertEqual(get_user_default_seq_type(user), 'AS')

    def test_unauthenticated_returns_ss(self):
        """Anonymous/unauthenticated user returns 'SS'."""
        from app01.views import get_user_default_seq_type
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(get_user_default_seq_type(AnonymousUser()), 'SS')


class BuildComboReTests(TestCase):
    """CQ-07/08 — build_combo_re / normalize_tmp_seq_with_combo DB caching."""

    def setUp(self):
        DeliveryModule.objects.get_or_create(keyword='C16-NH', defaults={'type_code': 'Lipid'})
        SeqModule.objects.get_or_create(keyword='Am', defaults={'base_char': 'A'})

    def test_build_combo_re_returns_compiled_pattern(self):
        """build_combo_re() returns a compiled regex that matches known combos."""
        import re
        combo_re = build_combo_re()
        self.assertIsNotNone(combo_re)
        self.assertIsInstance(combo_re, type(re.compile('')))
        # Should match 'Am-C16-NH' (SeqModule left, DeliveryModule right)
        self.assertIsNotNone(combo_re.search('Am-C16-NH'))

    def test_normalize_accepts_prebuilt_combo_re(self):
        """normalize_tmp_seq_with_combo accepts a pre-built combo_re param."""
        combo_re = build_combo_re()
        result = normalize_tmp_seq_with_combo('Am-C16-NH', combo_re=combo_re)
        # combo stripped → left token 'Am' kept, '-C16-NH' dropped
        self.assertNotIn('C16-NH', result)
        self.assertIn('AM', result)

    def test_normalize_without_prebuilt_still_works(self):
        """normalize_tmp_seq_with_combo still works without combo_re (backward compat)."""
        result = normalize_tmp_seq_with_combo('Am-C16-NH')
        self.assertNotIn('C16-NH', result)
        self.assertIn('AM', result)

    def test_prebuilt_and_fresh_give_same_result(self):
        """Pre-built combo_re gives the same result as building fresh."""
        seq = 'AmUmGm-C16-NH'
        prebuilt = normalize_tmp_seq_with_combo(seq, combo_re=build_combo_re())
        fresh = normalize_tmp_seq_with_combo(seq)
        self.assertEqual(prebuilt, fresh)


# ── Permission Redesign: Model Tests ──────────────────────────────────────────

class LmsUserRoleTests(TestCase):
    """LmsUser new role fields and helper methods."""

    def _make_user(self, username, user_type, module_permissions=''):
        return LmsUser.objects.create_user(
            username=username, password='pass',
            user_type=user_type,
            module_permissions=module_permissions,
        )

    def test_superadmin_can_manage_all_modules(self):
        u = self._make_user('sa', 'superadmin')
        for m in ('delivery', 'seq', 'linker'):
            self.assertTrue(u.can_manage_module(m))

    def test_user_without_module_perms_cannot_manage(self):
        u = self._make_user('u', 'user')
        for m in ('delivery', 'seq', 'linker'):
            self.assertFalse(u.can_manage_module(m))

    def test_user_with_delivery_perm_only(self):
        u = self._make_user('u2', 'user', module_permissions='delivery')
        self.assertTrue(u.can_manage_module('delivery'))
        self.assertFalse(u.can_manage_module('seq'))
        self.assertFalse(u.can_manage_module('linker'))

    def test_sub_admin_with_no_explicit_module_perms(self):
        u = self._make_user('pi', 'sub_admin')
        for m in ('delivery', 'seq', 'linker'):
            self.assertFalse(u.can_manage_module(m))

    def test_is_superuser_flag_overrides_module_check(self):
        u = self._make_user('django_su', 'user')
        u.is_superuser = True
        u.save()
        self.assertTrue(u.can_manage_module('delivery'))

    def test_user_type_choices_are_three_values(self):
        choices = dict(LmsUser._meta.get_field('user_type').choices)
        self.assertEqual(set(choices.keys()), {'superadmin', 'sub_admin', 'user'})


class ProjectAccessRequestModelTests(TestCase):
    """ProjectAccessRequest basic model behaviour."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='requester', password='pass', user_type='user'
        )
        self.admin = LmsUser.objects.create_user(
            username='sa', password='pass', user_type='superadmin'
        )

    def test_create_pending_request(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user,
            project_codes='BPR-350,BPR-3T03',
            note='need access',
        )
        self.assertEqual(req.status, 'pending')
        self.assertIsNone(req.reviewed_by)

    def test_approve_request_updates_fields(self):
        from app01.models import ProjectAccessRequest
        from django.utils import timezone
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        req.status = 'approved'
        req.reviewed_by = self.admin
        req.reviewed_at = timezone.now()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.reviewed_by, self.admin)

    def test_default_ordering_newest_first(self):
        from app01.models import ProjectAccessRequest
        r1 = ProjectAccessRequest.objects.create(user=self.user, project_codes='A')
        r2 = ProjectAccessRequest.objects.create(user=self.user, project_codes='B')
        qs = list(ProjectAccessRequest.objects.all())
        self.assertEqual(qs[0], r2)
        self.assertEqual(qs[1], r1)


class PermissionHelperTests(TestCase):
    """user_can_edit_delivery and _is_superadmin helper behaviour."""

    def setUp(self):
        self.seq = Sequence.objects.create(
            rm_code='RM0001', seq='AUGC', seq_type='SS'
        )
        self.delivery = Delivery.objects.create(
            sequence=self.seq,
            seq_type='SS',
            modify_seq='AmUmGmCm',
            linker_seq='AmUmGmCm',
            project='BPR-350',
            duplex_id='BP000001',
        )
        DeliveryProject.objects.get_or_create(delivery=self.delivery, project_code='BPR-350')

        self.superadmin = LmsUser.objects.create_user(
            username='sa', password='p', user_type='superadmin'
        )
        self.sub_admin = LmsUser.objects.create_user(
            username='pi', password='p', user_type='sub_admin',
            permissions_project='BPR-350',
        )
        self.regular = LmsUser.objects.create_user(
            username='u', password='p', user_type='user',
            permissions_project='BPR-350',
        )
        self.no_project = LmsUser.objects.create_user(
            username='nop', password='p', user_type='sub_admin',
            permissions_project='OTHER',
        )

    def test_superadmin_can_edit_any_delivery(self):
        from app01.views import user_can_edit_delivery
        self.assertTrue(user_can_edit_delivery(self.superadmin, self.delivery))

    def test_sub_admin_can_edit_own_project(self):
        from app01.views import user_can_edit_delivery
        self.assertTrue(user_can_edit_delivery(self.sub_admin, self.delivery))

    def test_sub_admin_cannot_edit_other_project(self):
        from app01.views import user_can_edit_delivery
        self.assertFalse(user_can_edit_delivery(self.no_project, self.delivery))

    def test_regular_user_cannot_edit(self):
        from app01.views import user_can_edit_delivery
        self.assertFalse(user_can_edit_delivery(self.regular, self.delivery))

    def test_is_superuser_can_edit_delivery(self):
        """Django is_superuser flag should grant edit access regardless of user_type."""
        from app01.views import user_can_edit_delivery
        django_su = LmsUser.objects.create_user(
            username='django_su', password='p', user_type='user'
        )
        django_su.is_superuser = True
        django_su.save()
        self.assertTrue(user_can_edit_delivery(django_su, self.delivery))

    def test_user_can_edit_delivery_with_empty_project_links_returns_false(self):
        """Delivery with no project_links should not be editable by sub_admin."""
        from app01.views import user_can_edit_delivery
        from app01.models import DeliveryProject
        # Create a delivery with no project links
        orphan_delivery = Delivery.objects.create(
            sequence=self.seq,
            seq_type='SS',
            modify_seq='AmUmGmCm',
            linker_seq='AmUmGmCm',
            project='BPR-350',
            duplex_id='BP999999',
        )
        # Ensure no DeliveryProject rows exist for it
        DeliveryProject.objects.filter(delivery=orphan_delivery).delete()
        self.assertFalse(user_can_edit_delivery(self.sub_admin, orphan_delivery))

    def test_get_permitted_delivery_qs_superadmin_gets_all(self):
        from app01.views import get_permitted_delivery_qs
        qs = get_permitted_delivery_qs(self.superadmin)
        self.assertIn(self.delivery, qs)

    def test_get_permitted_delivery_qs_user_with_project(self):
        from app01.views import get_permitted_delivery_qs
        qs = get_permitted_delivery_qs(self.sub_admin)
        self.assertIn(self.delivery, qs)

    def test_get_permitted_delivery_qs_user_no_projects(self):
        from app01.views import get_permitted_delivery_qs
        no_project_user = LmsUser.objects.create_user(
            username='nobody', password='p', user_type='user',
            permissions_project='',
        )
        qs = get_permitted_delivery_qs(no_project_user)
        self.assertEqual(qs.count(), 0)

    def test_user_can_access_duplex_superadmin(self):
        from app01.views import _user_can_access_duplex
        self.assertTrue(_user_can_access_duplex(self.superadmin, 'BP000001'))

    def test_user_can_access_duplex_sub_admin_with_project(self):
        from app01.views import _user_can_access_duplex
        self.assertTrue(_user_can_access_duplex(self.sub_admin, 'BP000001'))

    def test_user_can_access_duplex_no_project(self):
        from app01.views import _user_can_access_duplex
        no_project_user = LmsUser.objects.create_user(
            username='nobody2', password='p', user_type='user',
            permissions_project='',
        )
        self.assertFalse(_user_can_access_duplex(no_project_user, 'BP000001'))


class ViewPermissionGateTests(TestCase):
    """Ensure view guards enforce the new 3-role model."""

    def setUp(self):
        self.client_sa = self.client_class()
        self.client_pi = self.client_class()
        self.client_u  = self.client_class()

        self.sa = LmsUser.objects.create_user(
            username='sa_gate', password='p', user_type='superadmin'
        )
        self.pi = LmsUser.objects.create_user(
            username='pi_gate', password='p', user_type='sub_admin'
        )
        self.u = LmsUser.objects.create_user(
            username='u_gate', password='p', user_type='user'
        )
        self.client_sa.force_login(self.sa)
        self.client_pi.force_login(self.pi)
        self.client_u.force_login(self.u)

    # author_list — superadmin only
    def test_author_list_superadmin_200(self):
        r = self.client_sa.get('/author_list/')
        self.assertEqual(r.status_code, 200)

    def test_author_list_sub_admin_redirects(self):
        r = self.client_pi.get('/author_list/')
        self.assertIn(r.status_code, [302, 403])

    def test_author_list_user_redirects(self):
        r = self.client_u.get('/author_list/')
        self.assertIn(r.status_code, [302, 403])

    # delete_experiment — sub_admin+
    def test_delete_experiment_user_redirects(self):
        r = self.client_u.post('/experiment/delete/9999/')
        # Must not 200 — either 403 or redirect with error message
        self.assertNotEqual(r.status_code, 200)

    def test_clone_delivery_user_gets_403(self):
        """user role cannot clone deliveries."""
        r = self.client_u.get('/clone_delivery/', {'strand_id': 'BP000001'})
        self.assertEqual(r.status_code, 403)

    def test_clone_delivery_sub_admin_does_not_get_403(self):
        """sub_admin role should pass the role gate (project check may still reject)."""
        r = self.client_pi.get('/clone_delivery/', {'strand_id': 'BP000001'})
        # 403 would mean the role gate rejected; anything else means it passed the gate
        self.assertNotEqual(r.status_code, 403)

    def test_confirm_share_get_user_redirects(self):
        """user role cannot view the share confirmation page."""
        r = self.client_u.get('/confirm_share/')
        self.assertIn(r.status_code, [302, 403])

    def test_confirm_share_post_user_redirects(self):
        """user role cannot POST to confirm_share."""
        r = self.client_u.post('/confirm_share/', {})
        self.assertIn(r.status_code, [302, 403])

    # register sets role to 'user' regardless of POST data
    def test_register_always_creates_user_role(self):
        r = self.client_class().post('/register/', {
            'username': 'newbie_gate',
            'email': 'newbie_gate@test.com',
            'password': 'pass123',
            'user_type': 'superadmin',   # should be ignored
            'permissions_project': '',
        })
        u = LmsUser.objects.filter(username='newbie_gate').first()
        self.assertIsNotNone(u)
        self.assertEqual(u.user_type, 'user')


class ProfileAndApprovalViewTests(TestCase):
    """Profile page, project access request, and approval workflow."""

    def setUp(self):
        self.sa = LmsUser.objects.create_user(
            username='sa_prof', password='p', user_type='superadmin'
        )
        self.user = LmsUser.objects.create_user(
            username='u_prof', password='p', user_type='user',
            permissions_project='',
        )
        self.client_sa = self.client_class()
        self.client_u  = self.client_class()
        self.client_sa.force_login(self.sa)
        self.client_u.force_login(self.user)

    def test_profile_page_loads_for_regular_user(self):
        r = self.client_u.get('/profile/')
        self.assertEqual(r.status_code, 200)

    def test_superadmin_redirected_from_profile(self):
        r = self.client_sa.get('/profile/')
        self.assertIn(r.status_code, [302, 200])
        if r.status_code == 302:
            self.assertIn('author_list', r['Location'])

    def test_submit_project_request_creates_pending(self):
        from app01.models import ProjectAccessRequest
        r = self.client_u.post('/request_project/', {
            'project_codes': 'BPR-350,BPR-3T03',
            'note': 'I need access',
        })
        self.assertIn(r.status_code, [302, 200])
        req = ProjectAccessRequest.objects.filter(user=self.user).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, 'pending')
        self.assertEqual(req.project_codes, 'BPR-350,BPR-3T03')

    def test_approve_request_updates_permissions_project(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        r = self.client_sa.post(f'/approve_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.assertIn(r.status_code, [302, 200])
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertIsNotNone(req.reviewed_at)
        self.user.refresh_from_db()
        self.assertIn('BPR-350', self.user.permissions_project)

    def test_double_approve_does_not_duplicate_permissions(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(user=self.user, project_codes='BPR-350')
        self.client_sa.post(f'/approve_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.client_sa.post(f'/approve_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.user.refresh_from_db()
        parts = [p for p in (self.user.permissions_project or '').split(',') if p]
        self.assertEqual(parts.count('BPR-350'), 1)

    def test_reject_request_does_not_grant_permissions(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-999'
        )
        self.client_sa.post(f'/approve_request/{req.id}/', {
            'action': 'reject',
            'review_note': 'not authorised',
        })
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.user.refresh_from_db()
        self.assertNotIn('BPR-999', self.user.permissions_project or '')

    def test_only_superadmin_can_approve(self):
        from app01.models import ProjectAccessRequest
        req = ProjectAccessRequest.objects.create(
            user=self.user, project_codes='BPR-350'
        )
        r = self.client_u.post(f'/approve_request/{req.id}/', {
            'action': 'approve',
        })
        self.assertIn(r.status_code, [302, 403])
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')  # unchanged


class ModulePermissionRequestModelTests(TestCase):
    """ModulePermissionRequest basic model behaviour."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='requester2', password='pass', user_type='user'
        )
        self.admin = LmsUser.objects.create_user(
            username='sa2', password='pass', user_type='superadmin'
        )

    def test_create_pending_request(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user,
            modules_requested='delivery,seq',
        )
        self.assertEqual(req.status, 'pending')
        self.assertIsNone(req.reviewed_by)
        self.assertIsNone(req.reviewed_at)

    def test_str_includes_username_and_modules(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='linker'
        )
        s = str(req)
        self.assertIn('requester2', s)
        self.assertIn('linker', s)

    def test_default_ordering_newest_first(self):
        from app01.models import ModulePermissionRequest
        r1 = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r2 = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='seq'
        )
        qs = list(ModulePermissionRequest.objects.all())
        self.assertEqual(qs[0], r2)
        self.assertEqual(qs[1], r1)

    def test_reviewed_fields_update(self):
        from app01.models import ModulePermissionRequest
        from django.utils import timezone
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        req.status = 'approved'
        req.reviewed_by = self.admin
        req.reviewed_at = timezone.now()
        req.save()
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.reviewed_by, self.admin)
        self.assertIsNotNone(req.reviewed_at)


class LogoutViewTests(TestCase):
    """Logout view: POST-only, clears session, redirects to login."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='logout_test_user', password='pass', user_type='user'
        )

    def test_get_returns_405(self):
        self.client.login(username='logout_test_user', password='pass')
        r = self.client.get('/logout/')
        self.assertEqual(r.status_code, 405)

    def test_post_redirects_to_login(self):
        self.client.login(username='logout_test_user', password='pass')
        r = self.client.post('/logout/')
        self.assertRedirects(r, '/login/', fetch_redirect_response=False)

    def test_post_clears_authentication(self):
        self.client.login(username='logout_test_user', password='pass')
        self.client.post('/logout/')
        # Subsequent request to a login-required page should redirect
        r = self.client.get('/profile/')
        self.assertNotEqual(r.status_code, 200)  # no longer authenticated


class ModuleRequestWorkflowTests(TestCase):
    """request_module_access and approve_module_request views."""

    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='mod_requester', password='pass', user_type='user',
            module_permissions='',
        )
        self.admin = LmsUser.objects.create_user(
            username='mod_sa', password='pass', user_type='superadmin',
        )
        self.client_u = self.client_class()
        self.client_u.login(username='mod_requester', password='pass')
        self.client_sa = self.client_class()
        self.client_sa.login(username='mod_sa', password='pass')

    def test_user_can_submit_module_request(self):
        from app01.models import ModulePermissionRequest
        r = self.client_u.post('/request_module/', {
            'modules_requested': ['delivery', 'seq'],
            'note': 'need access',
        })
        self.assertIn(r.status_code, [302, 200])
        req = ModulePermissionRequest.objects.filter(user=self.user).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, 'pending')
        self.assertIn('delivery', req.modules_requested)

    def test_duplicate_pending_blocked(self):
        from app01.models import ModulePermissionRequest
        ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r = self.client_u.post('/request_module/', {
            'modules_requested': ['seq'],
        })
        self.assertIn(r.status_code, [302, 200])
        # Still only one pending request
        self.assertEqual(
            ModulePermissionRequest.objects.filter(user=self.user, status='pending').count(),
            1,
        )

    def test_empty_modules_rejected(self):
        from app01.models import ModulePermissionRequest
        r = self.client_u.post('/request_module/', {'modules_requested': []})
        self.assertIn(r.status_code, [302, 200])
        self.assertEqual(ModulePermissionRequest.objects.filter(user=self.user).count(), 0)

    def test_superadmin_cannot_submit_module_request(self):
        from app01.models import ModulePermissionRequest
        r = self.client_sa.post('/request_module/', {
            'modules_requested': ['delivery'],
        })
        self.assertIn(r.status_code, [302, 200])
        self.assertEqual(ModulePermissionRequest.objects.filter(user=self.admin).count(), 0)

    def test_approve_module_request_grants_permissions(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery,linker'
        )
        r = self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.assertIn(r.status_code, [302, 200])
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.user.refresh_from_db()
        self.assertIn('delivery', self.user.module_permissions)
        self.assertIn('linker', self.user.module_permissions)

    def test_approve_merges_with_existing_permissions(self):
        from app01.models import ModulePermissionRequest
        self.user.module_permissions = 'seq'
        self.user.save()
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
            'review_note': '',
        })
        self.user.refresh_from_db()
        mods = {m for m in self.user.module_permissions.split(',') if m}
        self.assertIn('seq', mods)
        self.assertIn('delivery', mods)

    def test_double_approve_no_duplicate_modules(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.client_sa.post(f'/approve_module_request/{req.id}/', {'action': 'approve', 'review_note': ''})
        self.user.refresh_from_db()
        mods = [m for m in self.user.module_permissions.split(',') if m]
        self.assertEqual(mods.count('delivery'), 1)

    def test_reject_does_not_grant_permissions(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='seq'
        )
        self.client_sa.post(f'/approve_module_request/{req.id}/', {
            'action': 'reject',
            'review_note': 'not approved',
        })
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.user.refresh_from_db()
        self.assertNotIn('seq', self.user.module_permissions or '')

    def test_non_superadmin_cannot_approve(self):
        from app01.models import ModulePermissionRequest
        req = ModulePermissionRequest.objects.create(
            user=self.user, modules_requested='delivery'
        )
        r = self.client_u.post(f'/approve_module_request/{req.id}/', {
            'action': 'approve',
        })
        self.assertIn(r.status_code, [302, 403])
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
