from django.db import migrations


def _canonicalize(raw_id, project_code):
    if not raw_id or not project_code:
        return raw_id
    if raw_id.startswith(f'BPR{project_code}-'):
        return raw_id
    serial = None
    for prefix in (
        f'BPR_{project_code}',
        f'BPR-{project_code}',
        f'BPR{project_code}-',
        f'BPR{project_code}',
        project_code,
    ):
        if raw_id.startswith(prefix):
            serial = raw_id[len(prefix):]
            break
    if serial is None:
        return raw_id
    serial = serial.lstrip('-')
    if not serial:
        return raw_id
    return f'BPR{project_code}-{serial}'


def migrate_ids(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        cur.execute(
            "SELECT compound_id, project FROM compound WHERE project != ''"
        )
        rows = cur.fetchall()

        # Build set of all current compound_ids so we can detect collisions
        existing_ids = {r[0] for r in rows}

        # Separate rows that need renaming into two passes:
        # Pass 1: rows whose canonical ID does NOT yet exist → simple rename
        # Pass 2: rows whose canonical ID ALREADY exists (collision) → merge + delete
        pass1 = []
        pass2 = []
        for old_id, project in rows:
            new_id = _canonicalize(old_id, project)
            if new_id == old_id:
                continue
            if new_id in existing_ids:
                pass2.append((old_id, new_id))
            else:
                pass1.append((old_id, new_id))
                # The new_id will exist after this rename, update tracking set
                existing_ids.add(new_id)
                existing_ids.discard(old_id)

        for old_id, new_id in pass1:
            cur.execute(
                "UPDATE strand SET compound_id=%s WHERE compound_id=%s",
                [new_id, old_id],
            )
            cur.execute(
                "UPDATE experiment SET compound_id=%s WHERE compound_id=%s",
                [new_id, old_id],
            )
            cur.execute(
                "UPDATE compound SET compound_id=%s WHERE compound_id=%s",
                [new_id, old_id],
            )

        # Pass 2: collision cases — canonical target already exists.
        # Re-point child rows to the canonical compound, then delete the duplicate.
        for old_id, new_id in pass2:
            cur.execute(
                "UPDATE strand SET compound_id=%s WHERE compound_id=%s",
                [new_id, old_id],
            )
            cur.execute(
                "UPDATE experiment SET compound_id=%s WHERE compound_id=%s",
                [new_id, old_id],
            )
            cur.execute(
                "DELETE FROM compound WHERE compound_id=%s",
                [old_id],
            )

        cur.execute("SET FOREIGN_KEY_CHECKS=1")


def reverse_ids(apps, schema_editor):
    pass  # PK renames are not reversible without a full snapshot


class Migration(migrations.Migration):

    dependencies = [
        ('app01', '0009_cleanup_upload_vocab'),
    ]

    operations = [
        migrations.RunPython(migrate_ids, reverse_ids),
    ]
