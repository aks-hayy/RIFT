import pathlib
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
APP = ANDROID / "app"
MAIN = APP / "src" / "main"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class AndroidScaffoldTests(unittest.TestCase):
    def test_gradle_project_is_declared(self) -> None:
        settings = (ANDROID / "settings.gradle.kts").read_text(encoding="utf-8")
        build = (APP / "build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('include(":app")', settings)
        self.assertIn("com.android.application", build)
        self.assertIn("minSdk = 26", build)
        self.assertIn("targetSdk = 36", build)
        self.assertIn('include(":runtime-llama")', settings)

    def test_manifest_is_https_only_and_service_is_private(self) -> None:
        manifest_path = MAIN / "AndroidManifest.xml"
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        permissions = {
            item.attrib[f"{ANDROID_NS}name"]
            for item in root.findall("uses-permission")
        }
        self.assertIn("android.permission.INTERNET", permissions)
        self.assertIn("android.permission.FOREGROUND_SERVICE", permissions)
        self.assertNotIn("android.permission.FOREGROUND_SERVICE_DATA_SYNC", permissions)

        application = root.find("application")
        self.assertIsNotNone(application)
        self.assertEqual(application.attrib[f"{ANDROID_NS}usesCleartextTraffic"], "false")
        self.assertEqual(
            application.attrib[f"{ANDROID_NS}networkSecurityConfig"],
            "@xml/network_security_config",
        )
        service = application.find("service")
        self.assertIsNotNone(service)
        self.assertEqual(service.attrib[f"{ANDROID_NS}exported"], "false")
        self.assertEqual(service.attrib[f"{ANDROID_NS}foregroundServiceType"], "shortService")

    def test_network_security_does_not_trust_cleartext_or_user_cas(self) -> None:
        config = ET.parse(MAIN / "res" / "xml" / "network_security_config.xml").getroot()
        base = config.find("base-config")
        self.assertIsNotNone(base)
        self.assertEqual(base.attrib["cleartextTrafficPermitted"], "false")
        sources = {
            item.attrib["src"]
            for item in base.findall("trust-anchors/certificates")
        }
        self.assertEqual(sources, {"system"})

    def test_runtime_boundaries_are_explicit(self) -> None:
        kotlin_root = MAIN / "kotlin" / "io" / "rift" / "mesh"
        runtime = (kotlin_root / "inference" / "LocalInferenceRuntime.kt").read_text(
            encoding="utf-8"
        )
        jni = (kotlin_root / "inference" / "LlamaCppJniRuntime.kt").read_text(
            encoding="utf-8"
        )
        lease = (kotlin_root / "routing" / "RouteLeaseStore.kt").read_text(
            encoding="utf-8"
        )
        remote = (kotlin_root / "inference" / "RemoteInferenceClient.kt").read_text(
            encoding="utf-8"
        )

        self.assertIn("Unavailable", runtime)
        self.assertIn('System.loadLibrary("rift_llama")', jni)
        self.assertIn("external fun", jni)
        self.assertIn("AndroidKeyStore", lease)
        self.assertIn("HttpsURLConnection", remote)
        self.assertNotIn("mock response", (runtime + jni + remote).lower())

        runtime_module = ANDROID / "runtime-llama" / "src" / "main" / "kotlin"
        contract = next(runtime_module.rglob("LocalInferenceRuntime.kt")).read_text(encoding="utf-8")
        self.assertIn("StateFlow<RuntimeState>", contract)
        self.assertIn("Flow<GenerationEvent>", contract)


if __name__ == "__main__":
    unittest.main()
