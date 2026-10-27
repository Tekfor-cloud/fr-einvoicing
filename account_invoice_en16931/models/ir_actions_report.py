# Copyright 2016-2026 Akretion France (http://www.akretion.com)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import io
import logging

from odoo import models
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter

logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        # It works, but:
        # - when you click on the "Print" button or use the "Print" menu,
        # the XML file is regenerated even when the invoice is read from the attachment.
        # - when you open the invoice from the attachment, you get the "original" XML
        # file
        collected_streams = super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids
        )
        if (
            collected_streams
            and res_ids
            and len(res_ids) == 1
            and self._is_invoice_report(report_ref)
            # and not self.env.context.get("regular_pdf_invoice")
        ):
            # Implementation strategy: we always generate PDF/A for invoices
            # whatever the format, because they plan to make PDF/A required
            # even when embedding a PDF invoice in an UBL or CII XML file
            move = self.env["account.move"].browse(res_ids)
            pdf_bytesio = collected_streams[move.id]["stream"]
            # Hack needed for qweb reports because wkhtmltopdf is unable to
            # produce valid PDF/A and we need valid PDF/A as input to the factur-x
            # lib in order to produce valid PDF/A3 as output
            odoo_reader = OdooPdfFileReader(pdf_bytesio)
            odoo_writer = OdooPdfFileWriter()
            odoo_writer.cloneReaderDocumentRoot(odoo_reader)
            try:
                # Call native method from odoo/tools/pdf/__init__.py
                # That's where the dirty work is located
                # This method requires the 'fonttools' python lib
                # pip install fonttools
                odoo_writer.convert_to_pdfa()
            except Exception as err:
                logger.warning(f"Failure in PDF/A conversion: {err}")
            metadata_dict = move._qweb_pdfa_prepare_metadata()
            logger.debug(f"metadata_dict={metadata_dict}")
            odoo_writer.add_file_metadata(
                move._qweb_pdfa_generate_xmp_bytes(metadata_dict)
            )
            move._qweb_pdfa_generate_txt_metadata(metadata_dict, odoo_writer)
            pdfa_bytesio = io.BytesIO()
            odoo_writer.write(pdfa_bytesio)
            pdf_bytesio.close()
            collected_streams[move.id]["stream"] = pdfa_bytesio
            pdf_bytesio = collected_streams[move.id]["stream"]
            logger.info(f"Qweb invoice report {move.display_name} converted to PDF/A")
            invoice_format = move._get_pdf_invoice_format()
            if invoice_format and not self.env.context.get("regular_pdf_invoice"):
                move._regular_pdf_invoice_to_en16931_pdf_invoice(
                    pdf_bytesio, invoice_format
                )
        return collected_streams
