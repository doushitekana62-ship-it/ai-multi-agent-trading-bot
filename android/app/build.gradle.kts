plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.mirei.app"
    compileSdk = 35

    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "com.mirei.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "0.1.2"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    flavorDimensions += "mode"

    productFlavors {
        create("paper") {
            dimension = "mode"
            applicationIdSuffix = ".paper"
            versionNameSuffix = "-paper"
            buildConfigField("String", "MIREI_MODE", "\"PAPER\"")
        }
        create("live") {
            dimension = "mode"
            applicationIdSuffix = ".live"
            versionNameSuffix = "-live"
            buildConfigField("String", "MIREI_MODE", "\"LIVE\"")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
