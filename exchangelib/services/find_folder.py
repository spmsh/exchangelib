from collections import OrderedDict

from ..util import create_element, set_xml_value, TNS
from ..version import EXCHANGE_2010
from .common import EWSAccountService, create_shape_element


class FindFolder(EWSAccountService):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/findfolder"""
    SERVICE_NAME = 'FindFolder'
    element_container_name = '{%s}Folders' % TNS
    supports_paging = True

    def call(self, folders, additional_fields, restriction, shape, depth, max_items, offset):
        """Find subfolders of a folder.

        Args:
          folders: the folders to act on
          additional_fields: the extra fields that should be returned with the folder, as FieldPath objects
          restriction: Restriction object that defines the filters for the query
          shape: The set of attributes to return
          depth: How deep in the folder structure to search for folders
          max_items: The maximum number of items to return
          offset: the offset relative to the first item in the item collection. Usually 0.

        Returns:
          XML elements for the matching folders

        """
        from ..folders import Folder
        roots = {f.root for f in folders}
        if len(roots) != 1:
            raise ValueError('FindFolder must be called with folders in the same root hierarchy (%r)' % roots)
        root = roots.pop()
        for elem in self._paged_call(
                payload_func=self.get_payload,
                max_items=max_items,
                expected_message_count=len(folders),
                **dict(
                    folders=folders,
                    additional_fields=additional_fields,
                    restriction=restriction,
                    shape=shape,
                    depth=depth,
                    page_size=self.chunk_size,
                    offset=offset,
                )
        ):
            if isinstance(elem, Exception):
                yield elem
                continue
            yield Folder.from_xml_with_root(elem=elem, root=root)

    def get_payload(self, folders, additional_fields, restriction, shape, depth, page_size, offset=0):
        findfolder = create_element('m:%s' % self.SERVICE_NAME, attrs=dict(Traversal=depth))
        foldershape = create_shape_element(
            tag='m:FolderShape', shape=shape, additional_fields=additional_fields, version=self.account.version
        )
        findfolder.append(foldershape)
        if self.account.version.build >= EXCHANGE_2010:
            indexedpageviewitem = create_element(
                'm:IndexedPageFolderView',
                attrs=OrderedDict([
                    ('MaxEntriesReturned', str(page_size)),
                    ('Offset', str(offset)),
                    ('BasePoint', 'Beginning'),
                ])
            )
            findfolder.append(indexedpageviewitem)
        else:
            if offset != 0:
                raise ValueError('Offsets are only supported from Exchange 2010')
        if restriction:
            findfolder.append(restriction.to_xml(version=self.account.version))
        parentfolderids = create_element('m:ParentFolderIds')
        set_xml_value(parentfolderids, folders, version=self.account.version)
        findfolder.append(parentfolderids)
        return findfolder
