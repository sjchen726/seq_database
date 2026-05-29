import json
import pandas as pd
from django.test import TestCase
from app01.models import Sequence, SeqModule, DeliveryModule, Delivery, DeliveryProject, LmsUser
from app01.views import (
    normalize_middle_brackets, run_preflight_check, group_sequences,
    auto_register_bare_sequences, check_duplicates,
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
