"""Remove comment records only when acceptance removed their last anchor."""
import posixpath
from urllib.parse import unquote
from lxml import etree
from .package import W, CT, R_NS, relationship_source, relationship_target
from .revisions import active_nodes

W14='{http://schemas.microsoft.com/office/word/2010/wordml}'
W15='{http://schemas.microsoft.com/office/word/2012/wordml}'
CID='{http://schemas.microsoft.com/office/word/2016/wordml/cid}'
CEX='{http://schemas.microsoft.com/office/word/2018/wordml/cex}'
META={W15+'commentsEx':('commentsExtended',W15+'paraId'),
      CID+'commentsIds':('commentsIds',CID+'paraId'),
      CEX+'commentsExtensible':('commentsExtensible',CEX+'durableId')}


def reference_ids(roots):
    return {n.get(W+'id') for root in roots.values() for n in active_nodes(root) if n.tag==W+'commentReference'}


def prune_comments(roots, names, before, stats):
    gone=before-reference_ids(roots)
    changed=set();removed=set();para_ids=set();empty_types={}
    if not gone:return removed,{}
    for name,root in roots.items():
        if root.tag==W+'comments':
            for node in list(root):
                if node.tag==W+'comment' and node.get(W+'id') in gone:
                    para_ids.update(p.get(W14+'paraId') for p in node.iter(W+'p') if p.get(W14+'paraId'))
                    root.remove(node);changed.add(name);stats['deleted_comments']+=1
            if name in changed and not len(root):empty_types[name]='comments'
        for node in list(root.iter(W+'commentRangeStart',W+'commentRangeEnd')):
            if node.get(W+'id') in gone:
                node.getparent().remove(node);changed.add(name)
    durable=set()
    for root in roots.values():
        if root.tag==CID+'commentsIds':
            durable.update(n.get(CID+'durableId') for n in root if n.get(CID+'paraId') in para_ids)
        if root.tag==W15+'commentsEx':
            if any(n.get(W15+'paraIdParent') in para_ids and n.get(W15+'paraId') not in para_ids for n in root):
                raise ValueError('Cannot delete comment with surviving threaded reply')
    for name,root in roots.items():
        if root.tag not in META:continue
        kind,key=META[root.tag];ids=durable if root.tag==CEX+'commentsExtensible' else para_ids
        for node in list(root):
            if node.get(key) in ids:
                root.remove(node);changed.add(name)
        if name in changed and not len(root):empty_types[name]=kind
    # Only expected relationships to emptied known comment parts may be removed.
    for name,root in roots.items():
        if not name.endswith('.rels'):continue
        source=relationship_source(name)
        for rel in list(root):
            if rel.get('TargetMode')=='External':continue
            target=relationship_target(source,rel.get('Target'))
            if target in empty_types:
                kind=empty_types[target]
                allowed={R_NS+'/comments','http://schemas.microsoft.com/office/2011/relationships/commentsExtended',
                         'http://schemas.microsoft.com/office/2016/09/relationships/commentsIds',
                         'http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible'}
                if rel.get('Type') not in allowed or not rel.get('Type').endswith('/'+kind):
                    raise ValueError('Unknown relationship pins deleted comment part: '+target)
                root.remove(rel);changed.add(name)
    for name in empty_types:
        rels=posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
        if rels in names:
            # Outgoing attachments are kept, but the now source-less rels must go.
            removed.add(rels)
        removed.add(name)
    types=roots['[Content_Types].xml']
    for node in list(types):
        if node.tag==CT+'Override' and unquote(node.get('PartName')).lstrip('/') in removed:
            types.remove(node);changed.add('[Content_Types].xml')
    for name in removed:roots.pop(name,None)
    return removed,{name:etree.tostring(roots[name],encoding='UTF-8',xml_declaration=True,standalone=True) for name in changed-removed}
