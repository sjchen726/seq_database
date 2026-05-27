"""
转录本定位工具 — 算法模块

对外接口：align_duplex(duplex_id, nm_accession, user, score_threshold) -> dict
内部：fetch_transcript_seq, get_ss_naked_dna, parse_mismatches, run_sw_alignment
"""
from __future__ import annotations


class TranscriptFetchError(Exception):
    """NCBI 拉取失败时抛出。"""


_COMP = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}


def fetch_transcript_seq(accession: str) -> str:
    """调用 NCBI Entrez efetch 拉取 FASTA，返回大写 DNA 字符串（T，不含 U）。
    失败时抛 TranscriptFetchError。"""
    from Bio import Entrez, SeqIO
    from django.conf import settings

    Entrez.email = getattr(settings, 'ENTREZ_EMAIL', 'admin@seqdb.local')
    try:
        handle = Entrez.efetch(
            db='nucleotide', id=accession.strip(),
            rettype='fasta', retmode='text'
        )
        record = SeqIO.read(handle, 'fasta')
        handle.close()
        return str(record.seq).upper()
    except Exception as exc:
        raise TranscriptFetchError(f'NCBI 获取失败（{accession}）: {exc}') from exc


def get_ss_naked_dna(duplex_id: str, user) -> tuple[str | None, str | None]:
    """返回 (naked_dna, sequence_rm_code)。
    优先取 SS 链裸序列（RNA→DNA, U→T）；
    无 SS 则取 AS 链裸序列的反向互补。
    两者都没有时返回 (None, None)。"""
    from app01.views import get_permitted_delivery_qs

    qs = get_permitted_delivery_qs(user).select_related('sequence')

    # 优先 SS
    ss_d = qs.filter(duplex_id=duplex_id, seq_type='SS').first()
    if ss_d and ss_d.sequence and ss_d.sequence.seq:
        dna = ss_d.sequence.seq.upper().replace('U', 'T')
        return dna, ss_d.sequence.rm_code

    # 降级到 AS 反向互补
    as_d = qs.filter(duplex_id=duplex_id, seq_type='AS').first()
    if as_d and as_d.sequence and as_d.sequence.seq:
        dna = as_d.sequence.seq.upper().replace('U', 'T')
        rc = ''.join(_COMP.get(b, 'N') for b in reversed(dna))
        return rc, as_d.sequence.rm_code

    return None, None


def parse_mismatches(seqA: str, seqB: str, query_len: int) -> list[dict]:
    """解析 SW 比对结果中的错配信息。
    seqA：query 对齐串（含 '-' gap）
    seqB：subject 对齐串（含 '-' gap）
    query_len：query 实际长度（不含 gap）
    返回列表，每项 {'pos': int, 'query_base': str, 'ref_base': str}，
    pos 从 query 5' 端（= query_len）向 3' 端（= 1）计数，输出按 3'→5' 排列。
    """
    result = []
    pos = query_len  # 5' 端位置
    for q, s in zip(seqA, seqB):
        if q == '-':
            continue  # query gap，位置不递减
        if q != s:
            result.append({
                'pos': pos,
                'query_base': _COMP.get(q, q),  # 显示 AS 链碱基（互补）
                'ref_base': s,
            })
        pos -= 1
    return list(reversed(result))  # 转为 3'→5' 顺序（pos 升序）


def run_sw_alignment(naked_dna: str, transcript_seq: str, score_threshold: int) -> dict | None:
    """运行 Smith-Waterman 局部比对。
    naked_dna：query，已是 DNA（T），大写
    transcript_seq：subject，已是 DNA（T），大写
    返回 None 表示无匹配（score < threshold 或无 alignment）。
    返回 dict：
        position      : '1234-1254'（1-based，含首尾）
        score         : float
        mismatch_count: int
        mismatches    : list[dict]
        alignment_str : pairwise2.format_alignment 原始字符串
    """
    from Bio import pairwise2

    alignments = pairwise2.align.localms(
        naked_dna, transcript_seq,
        1, 0, -10, -0.5          # match, mismatch, gap_open, gap_extend
    )
    if not alignments:
        return None

    best = max(alignments, key=lambda a: a.score)
    if best.score < score_threshold:
        return None

    mismatches = parse_mismatches(best.seqA, best.seqB, len(naked_dna))
    return {
        'position': f'{best.start + 1}-{best.end}',
        'score': best.score,
        'mismatch_count': len(mismatches),
        'mismatches': mismatches,
        'alignment_str': pairwise2.format_alignment(*best),
    }


def align_duplex(
    duplex_id: str,
    nm_accession: str,
    user,
    score_threshold: int | None = None,
) -> dict:
    """对外接口：给定 duplex_id + NM 登录号，返回完整比对结果 dict。
    字段：duplex_id, nm, sequence_rm_code, position, score,
          mismatch_count, mismatches, alignment_str, used_rc, error
    error 非 None 时表示失败，position 等字段为 None。
    """
    from django.conf import settings

    if score_threshold is None:
        score_threshold = getattr(settings, 'SW_SCORE_THRESHOLD', 15)

    result: dict = {
        'duplex_id': duplex_id,
        'nm': nm_accession.strip(),
        'sequence_rm_code': None,
        'position': None,
        'score': None,
        'mismatch_count': None,
        'mismatches': [],
        'alignment_str': '',
        'used_rc': False,
        'error': None,
    }

    try:
        naked_dna, seq_rm_code = get_ss_naked_dna(duplex_id, user)
        if not naked_dna:
            result['error'] = '无裸序列信息'
            return result
        result['sequence_rm_code'] = seq_rm_code

        transcript_seq = fetch_transcript_seq(nm_accession)
        sw = run_sw_alignment(naked_dna, transcript_seq, score_threshold)

        if sw is None:
            result['error'] = f'未找到匹配（得分 < {score_threshold}）'
            return result

        result.update(sw)

    except TranscriptFetchError as exc:
        result['error'] = str(exc)
    except Exception as exc:
        result['error'] = f'比对出错：{exc}'

    return result
