from .schemas import Answer


def validate_answer(answer: Answer, evidence: dict, searched: bool):
    errors = []
    if not searched:
        errors.append('必须先调用检索工具，不能直接依赖常识回答。')
    for c in answer.citations:
        doc = evidence.get(c.doc_id)
        if not doc:
            errors.append(f'{c.doc_id} 未成功读取，不能引用。')
            continue
        if c.version_date != doc['version_date']:
            errors.append(f'{c.doc_id} 引用版本不匹配。')
        chunk = next((ch for ch in doc['chunks'] if ch['chunk_id'] == c.chunk_id), None)
        if not chunk or c.quote not in chunk['text']:
            errors.append(f'{c.doc_id} 引用必须是指定片段中的连续原文，不得改写。')
    for item in [*answer.claims, *answer.conflicts]:
        if any(i < 0 or i >= len(answer.citations) for i in item.citation_indices):
            errors.append('引用索引越界，索引从 0 开始。')
    if answer.status == 'answered' and (not answer.claims or not answer.citations):
        errors.append('确定性回答必须包含关键结论及其证据。')
    if answer.status == 'conflict_unresolved':
        if not answer.conflicts or len({c.doc_id for c in answer.citations}) < 2:
            errors.append('冲突回答必须列出至少两份文档的依据和冲突说明。')
    if answer.status == 'needs_clarification' and not answer.clarification:
        errors.append('追问必须提供具体问题。')
    return errors
