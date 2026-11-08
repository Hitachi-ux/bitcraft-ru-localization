import base64, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import localize

class CatalogTest(unittest.TestCase):
    def make_catalog(self):
        obj='{"m_Hash":"6b3aedddc200617548234b0c8142d4e6","m_Crc":1949562651,"m_BundleSize":1426483502}'
        blob=b'header'+obj.encode('utf-16le')+b'\x07LUnity.ResourceManager'+b'other'
        return json.dumps({'m_ExtraDataString':base64.b64encode(blob).decode(),'other':'unchanged'}).encode()
    def test_updates_only_target_record_without_shifting_offsets(self):
        raw=self.make_catalog();out=localize.catalog_patch(raw,123,1433950434)
        a=json.loads(raw);b=json.loads(out);self.assertEqual(len(raw),len(out));self.assertEqual(a['other'],b['other'])
        blob=base64.b64decode(b['m_ExtraDataString']);self.assertIn('"m_Crc":123       '.encode('utf-16le'),blob);self.assertIn('"m_BundleSize":1433950434'.encode('utf-16le'),blob)
    def test_refuses_unknown_catalog(self):
        with self.assertRaises(RuntimeError):localize.catalog_patch(b'{"m_ExtraDataString":""}',1,1)

class SafetyTest(unittest.TestCase):
    def test_rejects_incompatible_files_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);aa,bundle,catalog,backup=localize.paths(root);bundle.parent.mkdir(parents=True);bundle.write_bytes(b'other version');catalog.write_bytes(b'other catalog')
            with patch.object(localize,'require_closed'),self.assertRaisesRegex(RuntimeError,'не совпадает'):localize.install(root)
            self.assertEqual(bundle.read_bytes(),b'other version');self.assertFalse(backup.exists())

if __name__=='__main__':unittest.main()