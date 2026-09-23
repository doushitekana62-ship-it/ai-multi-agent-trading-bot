package com.mirei.app.security

import android.content.Context
import android.util.Base64
import java.nio.charset.StandardCharsets
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore

data class ExchangeCredentials(
    val exchangeId: String,
    val apiKey: String,
    val apiSecret: String,
)

object LocalExchangeCredentialStore {
    private const val KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "mirei_exchange_credentials_v1"
    private const val PREFS = "mirei_exchange_credentials"
    private const val VALUE = "encrypted_credentials"

    fun save(context: Context, credentials: ExchangeCredentials) {
        val plaintext = listOf(credentials.exchangeId, credentials.apiKey, credentials.apiSecret)
            .joinToString("\n")
            .toByteArray(StandardCharsets.UTF_8)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(plaintext)
        val payload = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + "." +
            Base64.encodeToString(encrypted, Base64.NO_WRAP)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(VALUE, payload)
            .commit()
    }

    fun load(context: Context): ExchangeCredentials? {
        val payload = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(VALUE, null) ?: return null
        return runCatching {
            val parts = payload.split(".", limit = 2)
            require(parts.size == 2)
            val iv = Base64.decode(parts[0], Base64.DEFAULT)
            val encrypted = Base64.decode(parts[1], Base64.DEFAULT)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            val values = String(cipher.doFinal(encrypted), StandardCharsets.UTF_8).split("\n", limit = 3)
            require(values.size == 3)
            ExchangeCredentials(values[0], values[1], values[2])
        }.getOrNull()
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(VALUE).commit()
    }

    fun isConfigured(context: Context): Boolean = load(context) != null

    private fun key(): SecretKey {
        val store = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        val existing = store.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing

        val generator = KeyGenerator.getInstance("AES", KEYSTORE)
        generator.init(
            android.security.keystore.KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or
                    android.security.keystore.KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }
}
