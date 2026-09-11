package com.mirei.app.core

data class GlossaryTerm(val term: String, val definition: String)

object TradingGlossary {
    val terms: List<GlossaryTerm> = listOf(
        GlossaryTerm("Entry", "Harga saat posisi dibuka."),
        GlossaryTerm("Exit", "Harga saat posisi ditutup."),
        GlossaryTerm("Take Profit / TP", "Target harga untuk merealisasikan keuntungan."),
        GlossaryTerm("Stop Loss / SL", "Batas harga untuk membatasi kerugian. SL 0% di Mirei berarti unlimited hold sampai TP atau tutup manual."),
        GlossaryTerm("Risk/Reward", "Perbandingan potensi rugi dengan potensi untung dari satu posisi."),
        GlossaryTerm("1R", "Satu unit risiko yang dipakai untuk mengukur kapan trailing dapat diaktifkan."),
        GlossaryTerm("Trailing Stop", "Stop yang dapat diperketat mengikuti keuntungan dan tidak boleh dilonggarkan."),
        GlossaryTerm("Scalping", "Gaya trading dengan target kecil dan durasi posisi relatif singkat."),
        GlossaryTerm("Compounding", "Menggunakan kembali modal dan profit yang terealisasi untuk siklus berikutnya."),
        GlossaryTerm("Re-entry", "Membuka kembali posisi setelah posisi sebelumnya ditutup dan gate entry valid."),
        GlossaryTerm("PnL", "Profit and Loss, hasil untung/rugi posisi atau sesi."),
        GlossaryTerm("Unrealized PnL", "Untung/rugi posisi yang masih terbuka berdasarkan harga terbaru."),
        GlossaryTerm("Realized PnL", "Untung/rugi yang sudah terealisasi setelah posisi ditutup."),
        GlossaryTerm("Spread", "Selisih antara harga bid dan ask."),
        GlossaryTerm("Slippage", "Perbedaan antara harga acuan dan harga eksekusi simulasi."),
        GlossaryTerm("Momentum", "Ukuran arah/percepatan perubahan harga yang dipakai engine."),
        GlossaryTerm("Trend", "Ukuran kekuatan arah pergerakan pasar."),
        GlossaryTerm("Market Freshness", "Apakah snapshot market masih dalam batas usia yang dapat dipakai untuk keputusan."),
        GlossaryTerm("Gate", "Syarat risiko, freshness, posisi, dan market yang harus lolos sebelum entry."),
        GlossaryTerm("HOLD", "Keputusan untuk mempertahankan kondisi tanpa membuka/menutup posisi baru."),
        GlossaryTerm("BUY Decision", "Keputusan AI/agent untuk mengizinkan peluang masuk; bukan berarti order pasti terjadi."),
        GlossaryTerm("SELL Decision", "Keputusan AI/agent untuk keluar; berbeda dari jumlah close nyata."),
        GlossaryTerm("Actual Order", "Eksekusi yang benar-benar tercatat pada paper ledger, seperti OPEN atau CLOSE."),
        GlossaryTerm("Win Rate", "Persentase trade yang ditutup dengan PnL positif dari seluruh trade yang selesai."),
        GlossaryTerm("Top Up", "Menambahkan dana paper ke kas tanpa menghapus posisi yang sedang aktif."),
        GlossaryTerm("Resume / Lanjutkan", "Memulihkan portfolio dan posisi tersimpan lalu melanjutkan evaluasi memakai market terbaru."),
    )
}
