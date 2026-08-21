#include <jni.h>

extern "C" JNIEXPORT jlong JNICALL
Java_io_rift_mesh_runtime_NativeRuntimeBridge_createContext(
    JNIEnv*, jclass, jstring, jint) {
    return 0;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_io_rift_mesh_runtime_NativeRuntimeBridge_isRuntimeAvailable(JNIEnv*, jclass) {
#if RIFT_LLAMA_STUB
    return JNI_FALSE;
#else
    return JNI_TRUE;
#endif
}

extern "C" JNIEXPORT jstring JNICALL
Java_io_rift_mesh_runtime_NativeRuntimeBridge_generate(
    JNIEnv* env, jclass, jlong, jstring, jint, jfloat) {
    return env->NewStringUTF("");
}

extern "C" JNIEXPORT void JNICALL
Java_io_rift_mesh_runtime_NativeRuntimeBridge_destroyContext(
    JNIEnv*, jclass, jlong) {}
