# RIFT Mesh Android

This module is the Android node/client boundary for the RIFT Elastic Intelligence Mesh.

It provides:

- mDNS controller discovery for `_rift-controller._tcp.`
- explicit fingerprint and pairing-code approval UI
- an HTTPS-only controller and remote inference client
- consent-controlled WorkManager telemetry and a bounded short-service generation host
- Android Keystore-backed encrypted route-lease storage
- deterministic local-first route policy
- a `LocalInferenceRuntime` boundary for an optional llama.cpp JNI library

The app never synthesizes local inference output. `LlamaCppJniRuntime` reports an explicit
unavailable state unless a real `librift_llama.so` implementation and a model file are present.

## Build

Prerequisites: JDK 17, Android SDK 36, NDK 29, and Gradle 8.13. Open `android/` in Android Studio,
or use an installed Gradle distribution:

```text
gradle testDebugUnitTest
gradle assembleDebug
```

The `:runtime-llama` module is the stable integration boundary. It currently builds a safe native
stub that reports the runtime as unavailable; the next native milestone pins and links an upstream
llama.cpp commit for `arm64-v8a` and debug `x86_64`.

## Security posture

- Cleartext traffic is disabled in both the manifest and network security policy.
- Only system certificate authorities are trusted by the default network stack.
- Discovery produces untrusted sightings. Enrollment requires explicit code and fingerprint review.
- Telemetry is opt-in, private to the app, sequence ordered, and requires a node-scoped credential.
- Cached route bearer tokens are encrypted using AES-GCM keys held by Android Keystore.

Controller-issued client certificates and certificate rotation are controller integration work;
until those contracts are connected, this module is a statically verified scaffold, not a claim of
physical-device mesh acceptance.
