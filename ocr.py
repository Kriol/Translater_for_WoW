import io
from typing import Any, cast

import winsdk.windows.graphics.imaging as imaging
import winsdk.windows.media.ocr as ocr
import winsdk.windows.storage.streams as streams


class WinRTOCR:
    def __init__(self, logger) -> None:
        self.logger = logger
        self.engine = ocr.OcrEngine.try_create_from_user_profile_languages()
        if not self.engine:
            self.logger.error("WinRT OCR engine was not initialized. Check installed Windows language packs.")

    async def recognize_text(self, pil_image) -> str:
        if not self.engine:
            return ""

        byte_io = io.BytesIO()
        pil_image.save(byte_io, format="PNG")
        byte_data = byte_io.getvalue()

        stream = streams.InMemoryRandomAccessStream()
        output_stream = cast(streams.IOutputStream, stream)
        writer = streams.DataWriter(output_stream)
        writer.write_bytes(cast(Any, byte_data))
        await writer.store_async()
        stream.seek(0)

        random_access_stream = cast(streams.IRandomAccessStream, stream)
        decoder = await imaging.BitmapDecoder.create_async(random_access_stream)
        bitmap = await decoder.get_software_bitmap_async()

        result = await self.engine.recognize_async(bitmap)  # type: ignore[attr-defined]
        return result.text.strip()
