"""Explicit API generation facts, independent of Git commit dates."""
import argparse
import hashlib
import json
from pathlib import Path

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


def advance(document, entities, sources):
    if document.get('schema_version') != 1:
        raise ValueError('Unsupported source-history index')
    canonical = json.dumps(dict(entities=entities, sources=sources), sort_keys=True, separators=(',', ':'))
    identity = hashlib.sha256(canonical.encode()).hexdigest()
    if document.get('generations') and document['generations'][-1].get('snapshot_id') == identity:
        return document, document['latest_generation']
    previous_entry = document['generations'][-1] if document['generations'] else {}
    same_source_version = bool(sources.get('official_config_version') and sources.get('official_config_version') == previous_entry.get('sources', {}).get('official_config_version'))
    previous = document.get('comparison_base_entities', document.get('latest_entities', {})) if same_source_version else document.get('latest_entities', {})
    base_generation = document.get('comparison_base_generation', previous_entry.get('base_generation')) if same_source_version else document.get('latest_generation')
    additions = [dict(category=c, entity_id=i) for c in CATEGORIES for i in sorted(set(entities[c]) - set(previous.get(c, [])))]
    entry = dict(generation_id=identity, snapshot_id=identity, base_generation=base_generation, sources=sources, additions=additions)
    # A->B->A is a distinct batch with a distinct explicit predecessor.
    if any(e['generation_id'] == identity for e in document['generations']):
        identity = hashlib.sha256((identity + ':' + str(document.get('latest_generation'))).encode()).hexdigest()
        entry['generation_id'] = identity
    result = dict(document, generations=[*document['generations'], entry], latest_generation=identity, latest_entities=entities, comparison_base_entities=previous, comparison_base_generation=base_generation)
    return result, identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--patch', required=True)
    parser.add_argument('--tooling', required=True)
    parser.add_argument('--official-config-version', required=True)
    args = parser.parse_args()
    document = json.loads(INDEX.read_text(encoding='utf-8'))
    updated, identity = advance(document, entity_ids(Path('data/v1/data')), vars(args))
    INDEX.write_text(json.dumps(updated, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(identity)


if __name__ == '__main__':
    main()
