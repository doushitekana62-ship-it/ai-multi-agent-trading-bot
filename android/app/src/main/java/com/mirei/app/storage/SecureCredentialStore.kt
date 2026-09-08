package com.mirei.app.storage

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureCredentialStore(context: Context) {
    private val preferences = context.getSharedPreferences("mirei_secure", Context.MODE_PRIVATE)

    fun put(exchangeId: String, apiKey: String, apiSecret: String) {
        val payload = "$apiKey\u0000$apiSecret".toByteArray(StandardCharsets.UTF_8)
        preferences.edit().putString(exchangeId, encrypt(payload)).apply()
    }

    fun get(exchangeId: String): Pair<String, String>? {
        val stored = preferences.getString(exchangeId, null) ?: return null
        val parts = decrypt(stored).toString(StandardCharsets.UTF_8).split('\u0000', limit = 2)
        return if (parts.size == 2) parts[0] to parts[1] else null
    }

    fun delete(exchangeId: String) {
        preferences.edit().remove(exchangeId).apply()
    }

    fun has(exchangeId: String): Boolean = preferences.contains(exchangeId)

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val existing = keyStore.getKey(KEY_ALIAS, null)
        if (existing is SecretKey) return existing

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    private fun encrypt(bytes: ByteArray): String {
        val cipher = Cipher.getInstance(CIPHER)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(bytes)
        return Base64.encodeToString(iv + encrypted, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): ByteArray {
        val packed = Base64.decode(encoded, Base64.NO_WRAP)
        val ivLength = 12
        require(packed.size > ivLength) { "Invalid encrypted credential" }
        val iv = packed.copyOfRange(0, ivLength)
        val ciphertext = packed.copyOfRange(ivLength, packed.size)
        val cipher = Cipher.getInstance(CIPHER)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext)
    }

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val KEY_ALIAS = "mirei_credentials_v1"
        private const val CIPHER = "AES/GCM/NoPadding"
    }
}
