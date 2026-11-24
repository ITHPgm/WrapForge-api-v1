plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

fun prop(name: String, default: String) = providers.gradleProperty(name).orElse(default)
fun xmlEscape(value: String) = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;")
fun javaEscape(value: String) = value.replace("\\", "\\\\").replace("\"", "\\\"")

val compileSdkValue = prop("compileSdk", "36").get().toInt()
val buildToolsVersionValue = prop("buildToolsVersion", "36.0.0").get()
val appIdValue = prop("applicationId", "com.wrapforge.generated")
val appNameValue = prop("appName", "Website App")
val startUrlValue = prop("startUrl", "https://example.com")
val allowedHostsValue = prop("allowedHosts", "example.com")
val orientationValue = prop("orientation", "portrait")
val allowScreenshotsValue = prop("allowScreenshots", "true")
val showLoadingValue = prop("showLoading", "true")
val allowZoomValue = prop("allowZoom", "true")
val downloadsEnabledValue = prop("downloadsEnabled", "true")
val fileUploadsEnabledValue = prop("fileUploadsEnabled", "true")
val javascriptEnabledValue = prop("javascriptEnabled", "true")
val externalLinksValue = prop("externalLinks", "in_app_browser")
val primaryColorValue = prop("primaryColor", "#635BFF")
val statusBarColorValue = prop("statusBarColor", "#101522")
val navigationBarColorValue = prop("navigationBarColor", "#101522")
val storeFileValue = providers.gradleProperty("storeFile")
val storePasswordValue = providers.gradleProperty("storePassword")
val keyAliasValue = providers.gradleProperty("keyAlias")
val keyPasswordValue = providers.gradleProperty("keyPassword")

android {
    namespace = "com.wrapforge.generated"
    compileSdk = compileSdkValue
    buildToolsVersion = buildToolsVersionValue
    defaultConfig {
        applicationId = appIdValue.get()
        minSdk = 24
        targetSdk = compileSdkValue
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "START_URL", "\"${javaEscape(startUrlValue.get())}\"")
        buildConfigField("String", "ALLOWED_HOSTS", "\"${javaEscape(allowedHostsValue.get())}\"")
        buildConfigField("String", "EXTERNAL_LINKS", "\"${javaEscape(externalLinksValue.get())}\"")
        buildConfigField("boolean", "ALLOW_SCREENSHOTS", allowScreenshotsValue.get())
        buildConfigField("boolean", "SHOW_LOADING", showLoadingValue.get())
        buildConfigField("boolean", "ALLOW_ZOOM", allowZoomValue.get())
        buildConfigField("boolean", "DOWNLOADS_ENABLED", downloadsEnabledValue.get())
        buildConfigField("boolean", "FILE_UPLOADS_ENABLED", fileUploadsEnabledValue.get())
        buildConfigField("boolean", "JAVASCRIPT_ENABLED", javascriptEnabledValue.get())
        resValue("string", "app_name", xmlEscape(appNameValue.get()))
        resValue("color", "wrapforge_primary", primaryColorValue.get())
        resValue("color", "wrapforge_status_bar", statusBarColorValue.get())
        resValue("color", "wrapforge_navigation_bar", navigationBarColorValue.get())
        manifestPlaceholders["screenOrientation"] = when (orientationValue.get()) {
            "portrait" -> "portrait"
            "landscape" -> "landscape"
            "sensor" -> "fullSensor"
            else -> throw GradleException("Invalid orientation")
        }
    }
    buildFeatures { buildConfig = true }
    signingConfigs {
        create("wrapforgeRelease") {
            if (storeFileValue.isPresent) {
                storeFile = file(storeFileValue.get())
                storePassword = storePasswordValue.orNull
                keyAlias = keyAliasValue.orNull
                keyPassword = keyPasswordValue.orNull
                storeType = "JKS"
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            if (storeFileValue.isPresent) signingConfig = signingConfigs.getByName("wrapforgeRelease")
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.browser:browser:1.9.0")
}
