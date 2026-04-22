import pytest
from unittest.mock import patch, MagicMock
from notemaster.stt import transcribe


FAKE_AUDIO = b"\x00\x01\x02\x03fake audio bytes"


class TestTranscribe:
    def test_returns_transcript_string(self):
        mock_result = {"text": "  replication lag occurs when followers fall behind  "}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result):
            result = transcribe(FAKE_AUDIO, mime_type="audio/webm")
        assert result == "replication lag occurs when followers fall behind"

    def test_transcript_is_stripped(self):
        mock_result = {"text": "   leading and trailing spaces   "}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result):
            result = transcribe(FAKE_AUDIO, mime_type="audio/webm")
        assert result == "leading and trailing spaces"

    def test_called_with_temp_file_path(self):
        mock_result = {"text": "hello"}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result) as mock_fn:
            transcribe(FAKE_AUDIO, mime_type="audio/webm")
            call_args = mock_fn.call_args
            path_arg = call_args[0][0]
            assert isinstance(path_arg, str)
            assert len(path_arg) > 0

    def test_accepts_mp4_mime_type(self):
        mock_result = {"text": "ios safari audio"}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result):
            result = transcribe(FAKE_AUDIO, mime_type="audio/mp4")
        assert result == "ios safari audio"

    def test_accepts_webm_mime_type(self):
        mock_result = {"text": "desktop chrome audio"}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result):
            result = transcribe(FAKE_AUDIO, mime_type="audio/webm")
        assert result == "desktop chrome audio"

    def test_temp_file_is_cleaned_up(self):
        import os
        captured_path = []

        def fake_transcribe(path, **kwargs):
            captured_path.append(path)
            return {"text": "hello"}

        with patch("notemaster.stt.mlx_whisper.transcribe", side_effect=fake_transcribe):
            transcribe(FAKE_AUDIO, mime_type="audio/webm")

        assert not os.path.exists(captured_path[0])

    def test_empty_audio_returns_empty_string(self):
        mock_result = {"text": ""}
        with patch("notemaster.stt.mlx_whisper.transcribe", return_value=mock_result):
            result = transcribe(b"", mime_type="audio/webm")
        assert result == ""
