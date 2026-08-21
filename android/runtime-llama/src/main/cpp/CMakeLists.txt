cmake_minimum_required(VERSION 3.22.1)
project(rift_llama LANGUAGES CXX)

add_library(rift_llama SHARED rift_llama_jni.cpp)
target_compile_features(rift_llama PRIVATE cxx_std_17)
target_compile_definitions(rift_llama PRIVATE RIFT_LLAMA_STUB=1)
