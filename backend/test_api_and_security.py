"""
test_api_and_security.py
Comprehensive API and security verification suite:
- /api/health endpoint integrity and secrets protection
- /api/generate validation (empty, greetings, unrelated, valid)
- /api/compile validation (empty, invalid syntax, valid multi-instrument)
- /api/midi/{midi_id} path traversal prevention and 400/404 handling
- No arbitrary Python/shell execution on malicious payloads
- Concurrent request safety
"""

import unittest
import os
import re
import tempfile
import sys
import threading
from pathlib import Path
from fastapi import HTTPException

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import (
    app,
    health_check,
    generate_code,
    compile_code,
    download_midi,
    list_examples,
    GenerateRequest,
    CompileRequest,
)

class TestAPIAndSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Health Endpoint & Secrets Protection
    # -------------------------------------------------------------
    def test_health_endpoint_no_secrets_exposed(self):
        """Health check returns correct service status and never leaks API keys."""
        resp = health_check()
        self.assertEqual(resp["status"], "healthy")
        self.assertEqual(resp["service"], "SymphonyLang Studio API")
        self.assertIn("supported_instruments", resp)
        self.assertIn("Piano", resp["supported_instruments"])
        self.assertIn("Flute", resp["supported_instruments"])

        # Check response contains no secret keys
        resp_str = str(resp)
        self.assertNotIn("sk-", resp_str)
        self.assertNotIn("AIza", resp_str)
        self.assertNotIn("gsk_", resp_str)

    # -------------------------------------------------------------
    # 2. Generate Endpoint Validation
    # -------------------------------------------------------------
    def test_generate_endpoint_validation(self):
        """Test empty prompt validation, greetings, and valid compositions."""
        # Empty prompt -> 400 Bad Request
        with self.assertRaises(HTTPException) as cm:
            generate_code(GenerateRequest(prompt="   "))
        self.assertEqual(cm.exception.status_code, 400)

        # Greeting prompt -> conversational response without code
        res_greet = generate_code(GenerateRequest(prompt="hello"))
        self.assertFalse(res_greet.is_composition)
        self.assertIsNone(res_greet.code)
        self.assertIn("SymphonyLang", res_greet.explanation)

        # Unrelated query -> redirection without code
        res_unrelated = generate_code(GenerateRequest(prompt="What is the capital of Italy?"))
        self.assertFalse(res_unrelated.is_composition)
        self.assertIsNone(res_unrelated.code)
        self.assertIn("music", res_unrelated.explanation.lower())

        # Valid music prompt -> generates valid code
        res_music = generate_code(GenerateRequest(prompt="Create a cheerful piano melody at 120 BPM."))
        self.assertTrue(res_music.is_composition)
        self.assertIsNotNone(res_music.code)
        self.assertIn("TEMPO 120;", res_music.code)

    # -------------------------------------------------------------
    # 3. Compile Endpoint Validation
    # -------------------------------------------------------------
    def test_compile_endpoint_validation(self):
        """Test compilation with empty, invalid, and valid code."""
        # Empty code -> 400 Bad Request
        with self.assertRaises(HTTPException) as cm:
            compile_code(CompileRequest(source_code="   "))
        self.assertEqual(cm.exception.status_code, 400)

        # Invalid syntax -> success=False with clear error messages
        bad_code = "TEMPO 120;\nINSTRUMENT NonExistent;\nPLAY Z9 superfast;"
        res_bad = compile_code(CompileRequest(source_code=bad_code))
        self.assertFalse(res_bad.success)
        self.assertGreater(len(res_bad.errors), 0)
        self.assertIsNone(res_bad.midi_id)

        # Valid code -> success=True with timeline and midi_url
        good_code = "TEMPO 120;\nINSTRUMENT Piano;\nPLAY C4 quarter;\nPLAY E4 quarter;"
        res_good = compile_code(CompileRequest(source_code=good_code))
        self.assertTrue(res_good.success)
        self.assertIsNotNone(res_good.midi_id)
        self.assertTrue(res_good.midi_url.startswith("/api/midi/"))
        self.assertEqual(len(res_good.timeline), 2)
        self.assertGreater(res_good.total_duration_sec, 0.0)

    # -------------------------------------------------------------
    # 4. MIDI Download Security & Path Traversal Prevention
    # -------------------------------------------------------------
    def test_midi_download_security(self):
        """Strict validation prevents path traversal and returns 400/404 properly."""
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\win.ini",
            "../server.py",
            "12345",
            "../../outputs",
            "eval('import os')",
            "<script>alert(1)</script>",
        ]
        for attempt in traversal_attempts:
            with self.subTest(attempt=attempt):
                with self.assertRaises(HTTPException) as cm:
                    download_midi(attempt)
                self.assertEqual(cm.exception.status_code, 400)

        # Valid 32-character hex ID that does not exist -> 404 Not Found
        non_existent_hex = "a" * 32
        with self.assertRaises(HTTPException) as cm:
            download_midi(non_existent_hex)
        self.assertEqual(cm.exception.status_code, 404)

        # Valid existing ID -> returns FileResponse with audio/midi
        compile_res = compile_code(CompileRequest(
            source_code="TEMPO 100;\nINSTRUMENT Violin;\nPLAY A4 half;"
        ))
        self.assertTrue(compile_res.success)
        file_resp = download_midi(compile_res.midi_id)
        self.assertEqual(file_resp.media_type, "audio/midi")
        self.assertEqual(file_resp.filename, "symphony.mid")

    # -------------------------------------------------------------
    # 5. Injection Attack Resistance
    # -------------------------------------------------------------
    def test_injection_payloads_rejected(self):
        """Malicious payloads containing Python or shell commands are never executed."""
        payloads = [
            "__import__('os').system('echo pwned')",
            "exec('import sys; sys.exit(1)')",
            "eval('1+1')",
            "; DROP TABLE users; --",
        ]
        for p in payloads:
            with self.subTest(payload=p):
                res = compile_code(CompileRequest(source_code=p))
                self.assertFalse(res.success)
                self.assertGreater(len(res.errors), 0)

    # -------------------------------------------------------------
    # 6. Concurrent Request Safety
    # -------------------------------------------------------------
    def test_concurrent_compilation_safety(self):
        """Multiple simultaneous compilation requests do not corrupt shared state or crash."""
        results = []
        errors = []

        def worker(idx):
            try:
                code = f"TEMPO {100 + idx};\nINSTRUMENT Piano;\nPLAY C4 quarter;"
                resp = compile_code(CompileRequest(source_code=code))
                results.append((idx, resp.success, resp.midi_id))
            except Exception as e:
                errors.append((idx, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent workers failed: {errors}")
        self.assertEqual(len(results), 8)
        # Verify each worker received a unique MIDI ID
        midi_ids = [r[2] for r in results if r[1]]
        self.assertEqual(len(midi_ids), len(set(midi_ids)), "Duplicate MIDI IDs issued across concurrent requests!")

if __name__ == "__main__":
    unittest.main()

