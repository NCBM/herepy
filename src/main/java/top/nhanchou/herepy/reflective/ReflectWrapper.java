package top.nhanchou.herepy.reflective;

import java.lang.invoke.MethodType;
import java.lang.reflect.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Wraps java.lang.reflect types for Python-side consumption via JEP.
 * JEP cannot directly call reflection methods on Class objects, so this
 * provides a safe intermediary layer.
 */
public class ReflectWrapper {

    // ===== ReflectClass =====

    public static class ReflectClass {
        private final Class<?> clazz;

        public ReflectClass(Class<?> clazz) {
            this.clazz = clazz;
        }

        public String getName() { return clazz.getName(); }
        public String getSimpleName() { return clazz.getSimpleName(); }
        public String getCanonicalName() { return clazz.getCanonicalName(); }
        public String getPackageName() { return clazz.getPackageName(); }

        public ReflectClass getSuperclass() {
            Class<?> sup = clazz.getSuperclass();
            return sup != null ? new ReflectClass(sup) : null;
        }

        public List<ReflectClass> getInterfaces() {
            return Arrays.stream(clazz.getInterfaces())
                    .map(ReflectClass::new)
                    .collect(Collectors.toList());
        }

        public List<ReflectMethod> getMethods() {
            return Arrays.stream(clazz.getDeclaredMethods())
                    .filter(m -> Modifier.isPublic(m.getModifiers()) || Modifier.isProtected(m.getModifiers()))
                    .map(ReflectMethod::new)
                    .collect(Collectors.toList());
        }

        public List<ReflectField> getFields() {
            return Arrays.stream(clazz.getDeclaredFields())
                    .filter(f -> Modifier.isPublic(f.getModifiers()) || Modifier.isProtected(f.getModifiers()))
                    .map(ReflectField::new)
                    .collect(Collectors.toList());
        }

        public List<ReflectConstructor> getConstructors() {
            return Arrays.stream(clazz.getDeclaredConstructors())
                    .filter(c -> Modifier.isPublic(c.getModifiers()) || Modifier.isProtected(c.getModifiers()))
                    .map(ReflectConstructor::new)
                    .collect(Collectors.toList());
        }

        public List<ReflectTypeVariable> getTypeParameters() {
            return Arrays.stream(clazz.getTypeParameters())
                    .map(ReflectTypeVariable::new)
                    .collect(Collectors.toList());
        }

        public List<ReflectClass> getInnerClasses() {
            return Arrays.stream(clazz.getDeclaredClasses())
                    .filter(c -> Modifier.isPublic(c.getModifiers()) || Modifier.isProtected(c.getModifiers()))
                    .map(ReflectClass::new)
                    .collect(Collectors.toList());
        }

        public int getModifiers() { return clazz.getModifiers(); }
        public boolean isInterface() { return clazz.isInterface(); }
        public boolean isEnum() { return clazz.isEnum(); }
        public boolean isAbstract() { return Modifier.isAbstract(clazz.getModifiers()); }
        public boolean isFinal() { return Modifier.isFinal(clazz.getModifiers()); }
        public boolean isAnnotation() { return clazz.isAnnotation(); }

        public ReflectType getGenericSuperclass() {
            Type sup = clazz.getGenericSuperclass();
            return sup != null ? ReflectType.of(sup) : null;
        }

        public List<ReflectType> getGenericInterfaces() {
            return Arrays.stream(clazz.getGenericInterfaces())
                    .map(ReflectType::of)
                    .collect(Collectors.toList());
        }

        public Class<?> getRawClass() { return clazz; }
    }

    // ===== ReflectMethod =====

    public static class ReflectMethod {
        private final Method method;

        public ReflectMethod(Method method) {
            this.method = method;
        }

        public String getName() { return method.getName(); }
        public int getModifiers() { return method.getModifiers(); }
        public boolean isStatic() { return Modifier.isStatic(method.getModifiers()); }
        public boolean isFinal() { return Modifier.isFinal(method.getModifiers()); }
        public boolean isAbstract() { return Modifier.isAbstract(method.getModifiers()); }
        public boolean isDefault() { return method.isDefault(); }
        public boolean isVarArgs() { return method.isVarArgs(); }
        public boolean isSynchronized() { return Modifier.isSynchronized(method.getModifiers()); }

        public ReflectType getReturnType() {
            return ReflectType.of(method.getGenericReturnType());
        }

        public List<ReflectParameter> getParameters() {
            Parameter[] params = method.getParameters();
            Type[] genericTypes = method.getGenericParameterTypes();
            List<ReflectParameter> result = new ArrayList<>();
            for (int i = 0; i < params.length; i++) {
                boolean isVarArg = method.isVarArgs() && i == params.length - 1;
                result.add(new ReflectParameter(params[i], genericTypes[i], isVarArg));
            }
            return result;
        }

        public List<ReflectTypeVariable> getTypeParameters() {
            return Arrays.stream(method.getTypeParameters())
                    .map(ReflectTypeVariable::new)
                    .collect(Collectors.toList());
        }

        /**
         * The JVM descriptor, e.g. {@code (ILnet/minecraft/core/BlockPos;)V}. It separates two overloads that a
         * name cannot, and it is the key a mappings file publishes parameter names and docs under.
         */
        public String getDescriptor() {
            return MethodType.methodType(method.getReturnType(), method.getParameterTypes()).descriptorString();
        }
    }

    // ===== ReflectField =====

    public static class ReflectField {
        private final Field field;

        public ReflectField(Field field) {
            this.field = field;
        }

        public String getName() { return field.getName(); }
        public int getModifiers() { return field.getModifiers(); }
        public boolean isStatic() { return Modifier.isStatic(field.getModifiers()); }
        public boolean isFinal() { return Modifier.isFinal(field.getModifiers()); }

        public ReflectType getGenericType() {
            return ReflectType.of(field.getGenericType());
        }
    }

    // ===== ReflectConstructor =====

    public static class ReflectConstructor {
        private final Constructor<?> constructor;

        public ReflectConstructor(Constructor<?> constructor) {
            this.constructor = constructor;
        }

        public int getModifiers() { return constructor.getModifiers(); }
        public boolean isVarArgs() { return constructor.isVarArgs(); }

        public List<ReflectParameter> getParameters() {
            Parameter[] params = constructor.getParameters();
            Type[] genericTypes = constructor.getGenericParameterTypes();
            List<ReflectParameter> result = new ArrayList<>();
            // For inner class constructors, getGenericParameterTypes() omits the
            // synthetic outer-class parameter that getParameters() includes.
            int offset = params.length - genericTypes.length;
            for (int i = 0; i < params.length; i++) {
                boolean isVarArg = constructor.isVarArgs() && i == params.length - 1;
                Type genericType = (i >= offset) ? genericTypes[i - offset] : params[i].getType();
                result.add(new ReflectParameter(params[i], genericType, isVarArg));
            }
            return result;
        }

        public List<ReflectTypeVariable> getTypeParameters() {
            return Arrays.stream(constructor.getTypeParameters())
                    .map(ReflectTypeVariable::new)
                    .collect(Collectors.toList());
        }

        /** The JVM descriptor a mapping file keys a constructor by, spelled {@code <init>} there. */
        public String getDescriptor() {
            return MethodType.methodType(void.class, constructor.getParameterTypes()).descriptorString();
        }
    }

    // ===== ReflectParameter =====

    public static class ReflectParameter {
        private final Parameter parameter;
        private final Type genericType;
        private final boolean isVarArg;

        public ReflectParameter(Parameter parameter, Type genericType, boolean isVarArg) {
            this.parameter = parameter;
            this.genericType = genericType;
            this.isVarArg = isVarArg;
        }

        public String getName() { return parameter.getName(); }
        public boolean isNamePresent() { return parameter.isNamePresent(); }
        public boolean isVarArg() { return isVarArg; }

        public ReflectType getType() {
            // For varargs, unwrap the array to get the component type
            if (isVarArg && genericType instanceof GenericArrayType gat) {
                return ReflectType.of(gat.getGenericComponentType());
            }
            if (isVarArg && genericType instanceof Class<?> cls && cls.isArray()) {
                return ReflectType.of(cls.getComponentType());
            }
            return ReflectType.of(genericType);
        }
    }

    // ===== ReflectTypeVariable =====

    public static class ReflectTypeVariable {
        private final TypeVariable<?> typeVariable;

        public ReflectTypeVariable(TypeVariable<?> typeVariable) {
            this.typeVariable = typeVariable;
        }

        public String getName() { return typeVariable.getName(); }

        public List<ReflectType> getBounds() {
            return Arrays.stream(typeVariable.getBounds())
                    .filter(b -> !b.equals(Object.class))
                    .map(ReflectType::of)
                    .collect(Collectors.toList());
        }
    }

    // ===== ReflectType =====

    public static class ReflectType {
        private final Type type;

        private ReflectType(Type type) {
            this.type = type;
        }

        public static ReflectType of(Type type) {
            return new ReflectType(type);
        }

        public String getTypeName() { return type.getTypeName(); }

        public String getCanonicalName() {
            if (type instanceof Class<?> cls) {
                return cls.getCanonicalName() != null ? cls.getCanonicalName() : cls.getName();
            }
            if (type instanceof ParameterizedType pt) {
                return ((Class<?>) pt.getRawType()).getCanonicalName();
            }
            if (type instanceof TypeVariable<?> tv) {
                return tv.getName();
            }
            if (type instanceof GenericArrayType gat) {
                return ReflectType.of(gat.getGenericComponentType()).getCanonicalName() + "[]";
            }
            return type.getTypeName();
        }

        public boolean isClass() { return type instanceof Class<?>; }
        public boolean isParameterized() { return type instanceof ParameterizedType; }
        public boolean isTypeVariable() { return type instanceof TypeVariable; }
        public boolean isArray() {
            return (type instanceof Class<?> cls && cls.isArray())
                    || type instanceof GenericArrayType;
        }
        public boolean isWildcard() { return type instanceof WildcardType; }
        public boolean isPrimitive() { return type instanceof Class<?> cls && cls.isPrimitive(); }
        public boolean isVoid() { return type == void.class; }

        public ReflectType getRawType() {
            if (type instanceof ParameterizedType pt) {
                return ReflectType.of(pt.getRawType());
            }
            return this;
        }

        public List<ReflectType> getActualTypeArguments() {
            if (type instanceof ParameterizedType pt) {
                return Arrays.stream(pt.getActualTypeArguments())
                        .map(ReflectType::of)
                        .collect(Collectors.toList());
            }
            return List.of();
        }

        public ReflectType getComponentType() {
            if (type instanceof GenericArrayType gat) {
                return ReflectType.of(gat.getGenericComponentType());
            }
            if (type instanceof Class<?> cls && cls.isArray()) {
                return ReflectType.of(cls.getComponentType());
            }
            return null;
        }

        public int getArrayDimensions() {
            int dims = 0;
            Type t = type;
            while (true) {
                if (t instanceof GenericArrayType gat) {
                    dims++;
                    t = gat.getGenericComponentType();
                } else if (t instanceof Class<?> cls && cls.isArray()) {
                    dims++;
                    t = cls.getComponentType();
                } else {
                    break;
                }
            }
            return dims;
        }

        public List<ReflectType> getUpperBounds() {
            if (type instanceof WildcardType wt) {
                return Arrays.stream(wt.getUpperBounds())
                        .filter(b -> !b.equals(Object.class))
                        .map(ReflectType::of)
                        .collect(Collectors.toList());
            }
            return List.of();
        }

        public List<ReflectType> getLowerBounds() {
            if (type instanceof WildcardType wt) {
                return Arrays.stream(wt.getLowerBounds())
                        .map(ReflectType::of)
                        .collect(Collectors.toList());
            }
            return List.of();
        }
    }

    // ===== Utility =====

    public static ReflectClass forClass(Class<?> clazz) {
        return new ReflectClass(clazz);
    }

    public static ReflectType forType(Type type) {
        return ReflectType.of(type);
    }

    public static List<Class<?>> getLoadedClasses(ClassLoader classLoader) throws Exception {
        Field classesField = ClassLoader.class.getDeclaredField("classes");
        classesField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ArrayList<Class<?>> loadedClasses = (ArrayList<Class<?>>) classesField.get(classLoader);
        return new ArrayList<>(loadedClasses);
    }
}
