"""Explicit API generation facts, independent of Git commit dates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

CATEGORIES = ('achievement', 'pet', 'pet_skin', 'skill', 'mintmark', 'suit', 'equip')
INDEX = Path('data/v1/source-history-index.json')


def entity_ids(directory):
    """Read complete authoritative lists; stale detail aliases are not entities."""
    result = {}
    for category in CATEGORIES:
        resource = directory / category
        path = resource / 'index.json'
        if not path.is_file():
            raise ValueError('Missing complete resource list: ' + category)
        document = json.loads(path.read_text(encoding='utf-8'))
        items = document.get('results')
        if (
            not isinstance(items, list)
            or type(document.get('count')) is not int
            or document['count'] != len(items)
            or document.get('next') is not None
            or document.get('previous') is not None
        ):
            raise ValueError('Incomplete resource list: ' + category)
        ids = set()
        for item in items:
            identity = item.get('id') if isinstance(item, dict) else None
            if type(identity) is not int or identity <= 0 or identity in ids:
                raise ValueError('Invalid or duplicate resource ID: ' + category)
            detail = resource / str(identity) / 'index.json'
            if not detail.is_file():
                raise ValueError(f'Missing resource detail: {category}/{identity}')
            value = json.loads(detail.read_text(encoding='utf-8'))
            if type(value.get('id')) is not int or value['id'] != identity:
                raise ValueError(f'Resource detail identity mismatch: {category}/{identity}')
            ids.add(identity)
        result[category] = sorted(ids)
    return result



def validate_entities(entities):
    if not isinstance(entities, dict) or set(entities) != set(CATEGORIES):
        raise ValueError('Generation must contain all source categories')
    result = {}
    for category in CATEGORIES:
        values = entities[category]
        if not isinstance(values, list) or any(type(i) is not int or i <= 0 for i in values):
            raise ValueError('Invalid generation entity IDs: ' + category)
        if len(set(values)) != len(values):
            raise ValueError('Duplicate generation entity IDs: ' + category)
        result[category] = sorted(values)
    return result


def validate_sources(sources):
    for field in ('config', 'patch', 'tooling'):
        if not isinstance(sources.get(field), str) or not re.fullmatch('[0-9a-f]{40}', sources[field]):
            raise ValueError('Generation source requires a full commit SHA: ' + field)
    if not isinstance(sources.get('official_config_version'), str) or not re.fullmatch('[0-9]{14}', sources['official_config_version']):
        raise ValueError('Generation requires an explicit official configuration version')


def snapshot_id(entities, sources):
    canonical = json.dumps(dict(entities=entities, sources=sources), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_index(document, *, require_nonempty=False):
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document['schema_version'] != 1 or not isinstance(document.get('generations'), list):
        raise ValueError('Unsupported source-history index')
    entries = {}
    predecessor = None
    for entry in document['generations']:
        if not isinstance(entry, dict) or not isinstance(entry.get('sources'), dict):
            raise ValueError('Invalid generation record')
        identity = entry.get('generation_id')
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity) or identity in entries:
            raise ValueError('Invalid or duplicate generation ID')
        snapshot = entry.get('snapshot_id')
        if snapshot is not None:
            if not isinstance(snapshot, str) or not re.fullmatch('[0-9a-f]{64}', snapshot):
                raise ValueError('Invalid generation snapshot ID')
            allowed = {snapshot}
            if predecessor is not None:
                allowed.add(hashlib.sha256((snapshot + ':' + predecessor).encode()).hexdigest())
            if identity not in allowed:
                raise ValueError('Generation ID differs from snapshot/predecessor')
        if entry.get('base_generation') is not None and entry['base_generation'] not in entries:
            raise ValueError('Unknown or out-of-order generation predecessor')
        if type(entry.get('inventory_verified')) is not bool:
            raise ValueError('Generation inventory readiness must be explicit')
        if entry['inventory_verified']:
            seen = set()
            if not isinstance(entry.get('additions'), list):
                raise ValueError('Invalid generation additions')
            for item in entry['additions']:
                if not isinstance(item, dict) or item.get('category') not in CATEGORIES or type(item.get('entity_id')) is not int or item['entity_id'] <= 0:
                    raise ValueError('Invalid generation addition')
                pair = (item['category'], item['entity_id'])
                if pair in seen:
                    raise ValueError('Duplicate generation addition')
                seen.add(pair)
        entries[identity] = entry
        predecessor = identity
    if not entries:
        if require_nonempty or document.get('latest_generation') is not None:
            raise ValueError('A verified historical generation seed is required')
        return entries
    latest = document.get('latest_generation')
    if latest not in entries or latest != document['generations'][-1]['generation_id']:
        raise ValueError('Generation index latest pointer is inconsistent')
    current = entries[latest]
    if not current['inventory_verified']:
        raise ValueError('Latest generation inventory is not verified')
    entities = validate_entities(document.get('latest_entities'))
    previous = validate_entities(document.get('comparison_base_entities'))
    base = document.get('comparison_base_generation')
    if current.get('base_generation') != base or base is not None and (base not in entries or not entries[base]['inventory_verified']):
        raise ValueError('Generation comparison base is not verified')
    expected = {(c, i) for c in CATEGORIES for i in set(entities[c]) - set(previous[c])}
    if {(i['category'], i['entity_id']) for i in current['additions']} != expected:
        raise ValueError('Latest additions differ from explicit comparison entities')
    if current.get('snapshot_id') and current['snapshot_id'] != snapshot_id(entities, current['sources']):
        raise ValueError('Generation snapshot identity differs from source/entities')
    return entries


def receipt_generation(document, identity, config, patch, tooling):
    entries = validate_index(document, require_nonempty=True)
    if identity not in entries or identity != document['latest_generation']:
        raise ValueError('Receipt must identify the latest unique generation')
    entry = entries[identity]
    if not entry['inventory_verified']:
        raise ValueError('Receipt generation inventory is not verified')
    validate_sources(entry['sources'])
    if not entry.get('snapshot_id'):
        raise ValueError('New receipts require a generated snapshot identity')
    if any(entry['sources'][key] != expected for key, expected in [('config', config), ('patch', patch), ('tooling', tooling)]):
        raise ValueError('Receipt source and generation source differ')
    return entry


def advance(document, entities, sources):
    validate_index(document)
    entities = validate_entities(entities)
    identity = snapshot_id(entities, sources)
    if document.get('generations') and document['generations'][-1].get('snapshot_id') == identity:
        return document, document['latest_generation']
    previous_entry = document['generations'][-1] if document['generations'] else {}
    same_source_version = bool(sources.get('official_config_version') and sources.get('official_config_version') == previous_entry.get('sources', {}).get('official_config_version'))
    empty = {c: [] for c in CATEGORIES}
    previous = document.get('comparison_base_entities', document.get('latest_entities', empty)) if same_source_version else document.get('latest_entities', empty)
    previous = validate_entities(previous or empty)
    base_generation = document.get('comparison_base_generation', previous_entry.get('base_generation')) if same_source_version else document.get('latest_generation')
    additions = [dict(category=c, entity_id=i) for c in CATEGORIES for i in sorted(set(entities[c]) - set(previous[c]))]
    entry = dict(generation_id=identity, snapshot_id=identity, base_generation=base_generation, sources=sources, additions=additions, inventory_verified=True)
    # A->B->A is a distinct batch with a distinct explicit predecessor.
    if any(e['generation_id'] == identity for e in document['generations']):
        identity = hashlib.sha256((identity + ':' + str(document.get('latest_generation'))).encode()).hexdigest()
        entry['generation_id'] = identity
    result = dict(document, generations=[*document['generations'], entry], latest_generation=identity, latest_entities=entities, comparison_base_entities=previous, comparison_base_generation=base_generation)
    validate_index(result)
    return result, identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--patch', required=True)
    parser.add_argument('--tooling', required=True)
    parser.add_argument('--official-config-version', required=True)
    parser.add_argument('--index', type=Path, default=INDEX)
    parser.add_argument('--data-directory', type=Path, default=Path('data/v1/data'))
    args = parser.parse_args()
    sources = {key: getattr(args, key) for key in ('config', 'patch', 'tooling', 'official_config_version')}
    validate_sources(sources)
    before = args.index.read_bytes()
    document = json.loads(before)
    validate_index(document, require_nonempty=True)
    updated, identity = advance(document, entity_ids(args.data_directory), sources)
    encoded = (json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if encoded != before:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=args.index.parent, prefix='.generation-', delete=False) as output:
                temporary = Path(output.name)
                output.write(encoded)
            os.replace(temporary, args.index)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    print(identity)


if __name__ == '__main__':
    main()
