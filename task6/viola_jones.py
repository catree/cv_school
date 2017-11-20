#!/usr/bin/env python3
# coding: utf-8

"""
Viola Jones classifier.
Copyright (c) 2017 Mikhail Okunev (mishka.okunev@gmail.com)
Copyright (c) 2017 Paul Beltyukov (beltyukov.p.a@gmail.com)
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

#==============================================================================
import abc
import math
import numpy as np

import os
import os.path
from os import walk

import progressbar

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib import colors as cl


from skimage import io
from skimage.transform import resize

import random
from random import randint

#==============================================================================
def _get_all_images(starting_dir):
    images = []
    extensions = ["pgm", "jpeg", "jpg", "png"]
    for dir, _, filenames in walk(starting_dir):
        for filename in filenames:
            extension = os.path.splitext(filename)[1][1:]
            if extension in extensions:
                image = io.imread(os.path.join(dir, filename))
                images.append(image)
    return images

#==============================================================================
def get_all_images(starting_dir, img_file):
    
    if os.path.isfile(img_file):
        return np.load(img_file)
    else:
        ret = _get_all_images(starting_dir)
        np.save(img_file, ret)
        return ret

#==============================================================================
print('Loading images...')
positives = get_all_images('data/positives', 'data/pos_img.npy')
n_positives = len(positives)
negatives = get_all_images('data/negatives', 'data/neg_img.npy')
print('Done!')


#==============================================================================
# Зафиксируем размер окна, на котором будет работать классификатор
image_canonical_size = 24

#==============================================================================
# Вычтем из изображения среднее и поделим на стандартное отклонение
def normalize_image(image):
    mean, std = image.mean(), image.std()
    return ((image - mean) / std)


#==============================================================================
# Препроцессинг изображений с лицами
# 
# * Нормируем яркость, чтобы не учитывать освещенность
# * Преобразуем к 24 * 24

def prepare_positives(images, result_l):
    norm_images = [normalize_image(im.astype('float')) for im in images]
    resized_images = [resize(im, (result_l, result_l), mode='constant') for im in norm_images]
    return resized_images

#==============================================================================
pos_prep_fl = 'data/pos_prep.npy'

print('Prepare positive images...')
if os.path.isfile(pos_prep_fl):
    positives_prepared = np.load(pos_prep_fl)
else:
    positives_prepared = prepare_positives(positives, image_canonical_size)
    np.save(pos_prep_fl, positives_prepared)
print('Done!')

#==============================================================================
# Препроцессинг изображений без лиц
# 
# * Вырежем случайные квадраты из негативных изображений
# * Нормируем яркость
# * Преобразуем к 24 * 24

def prepare_negatives(images, sample_size, result_l):
    norm_images = [normalize_image(im.astype('float')) for im in images]
    crops = []
    for _ in range(0, sample_size):
        image_ind = randint(0, len(norm_images) - 1)
        image = norm_images[image_ind]
        w, h = image.shape
        max_r = min(w, h)
        r = random.randint(result_l, max_r)
        x, y = randint(0, w - max_r), randint(0, h - max_r)
        crop = image[x: x + r, y: y + r]
        crop = resize(crop, (result_l, result_l), mode='constant')
        crops.append(crop)
    return crops

#==============================================================================
# Возьмем столько же негативных изображений, сколько позитивных
n_negatives = n_positives

#==============================================================================
neg_prep_fl = 'data/neg_prep.npy'

print('Preparing negative images...')
if os.path.isfile(neg_prep_fl):
    negatives_prepared = np.load(neg_prep_fl)
else:
    negatives_prepared = prepare_negatives(negatives, n_negatives, image_canonical_size)
    np.save(neg_prep_fl, negatives_prepared)
print('Done!')

#==============================================================================
# Проверим, что данные имеют правильный формат
def image_has_correct_format(image, shape=(image_canonical_size, image_canonical_size)):
    return image.shape == shape

assert(len(positives_prepared) == n_positives)
assert(all([image_has_correct_format(im) for im in positives_prepared]))

assert(len(negatives_prepared) == n_negatives)
assert(all([image_has_correct_format(im) for im in negatives_prepared]))

#==============================================================================
# Интегральное изображение

class IntegralImage:
    def __init__(self, image):
        # hint: воспользуйтесь numpy.cumsum два раза, чтобы получить двумерную кумулятивную сумму
        h,w = image.shape
        
        ii = np.zeros((h + 1, w + 1), image.dtype)
        
        ii[1:, 1:] = np.cumsum(np.cumsum(image,0),1)
        
        self.integral_image = ii
    
    def sum(self, x1, y1, x2, y2):
        '''
        Сумма подмассива
        
        На входе:
            x1, y1 -- координаты левого нижнего угла прямоугольника запроса
            x2, y2 -- координаты верхнего правого угла прямоугольника запроса
            
        На выходе:
            Сумма подмассива [x1..x2, y1..y2]
        '''
        assert(x1 <= x2)
        assert(y1 <= y2)
        
        x2 = x2 + 1
        y2 = y2 + 1
        
        b11 = self.integral_image[x1, y1]
        b12 = self.integral_image[x2, y1]
        b21 = self.integral_image[x1, y2]
        b22 = self.integral_image[x2, y2]
        
        return b22 - b12 - b21 + b11

#==============================================================================
def get_integral_imgs(imgs, img_file):
    
    if os.path.isfile(img_file):
        return list(np.load(img_file))
    else:
        ret = [IntegralImage(im) for im in imgs]
        np.save(img_file, np.array(ret))
        return ret

#==============================================================================
print('Preparing integral images...')
integral_positives = get_integral_imgs(positives_prepared, 'data/pos_int.npy') #[IntegralImage(im) for im in positives_prepared]
integral_negatives = get_integral_imgs(negatives_prepared, 'data/neg_int.npy') #[IntegralImage(im) for im in negatives_prepared]
print('Done!')


#==============================================================================
# Признаки Хаара

# Общий интерфейс для всех классов признаков

class HaarFeature(object):
    __metaclass__ = abc.ABCMeta
    @abc.abstractmethod
    def compute_value(self, integral_image):
        '''
        Функция, вычисляющая и возвращающая значение признака
        
        На входе:
            integral_image -- IntegralImage
            
        На выходе:
            Значение признака
        '''
        pass
    
    def __repr__(self):
        return "Feature {}, {}, {}, {}".format(self.x_s, self.y_s, self.x_e, self.y_e)


#==============================================================================
class HaarFeatureVerticalTwoSegments(HaarFeature):
    def __init__(self, x, y, w, h):
        assert(h % 2 == 0)
        assert(x >= 0)
        assert(y >= 0)
        assert(w >= 2)
        assert(h >= 2)
        
        self.x_s = x
        self.x_e = x + w - 1
        
        self.y_s   = y
        self.y_m   = y + h // 2
        self.y_m_1 = y + h // 2 - 1
        self.y_e   = y + h - 1
        
    def compute_value(self, integral_image):
        s1 = integral_image.sum(self.x_s, self.y_s, self.x_e, self.y_m_1)
        s2 = integral_image.sum(self.x_s, self.y_m, self.x_e, self.y_e)
        return s1 - s2

#==============================================================================
class HaarFeatureVerticalThreeSegments(HaarFeature):
    
    def __init__(self, x, y, w, h):
        assert(h % 3 == 0)
        assert(x >= 0)
        assert(y >= 0)
        assert(w >= 2)
        assert(h >= 3)
        
        self.x_s  = x
        self.x_e  = x + w - 1
    
        self.y_s  = y
        self.y_m1 = y + h // 3
        self.y_m2 = y + 2 * h // 3 - 1
        self.y_e  = y + h - 1
        
    def compute_value(self, integral_image):
        s1 = integral_image.sum(self.x_s, self.y_s,  self.x_e, self.y_e)
        s2 = integral_image.sum(self.x_s, self.y_m1, self.x_e, self.y_m2)
        return s1 - 2.0 * s2

#==============================================================================
class HaarFeatureHorizontalTwoSegments(HaarFeature):
    
    def __init__(self, x, y, w, h):
        assert(h % 2 == 0)
        assert(x >= 0)
        assert(y >= 0)
        assert(w >= 2)
        assert(h >= 2)
        
        self.x_s   = x
        self.x_m   = x + w // 2
        self.x_m_1 = x + w // 2 - 1
        self.x_e   = x + w - 1
        
        self.y_s   = y
        self.y_e   = y + h - 1
        
    def compute_value(self, integral_image):
        s1 = integral_image.sum(self.x_m, self.y_s, self.x_e,   self.y_e)
        s2 = integral_image.sum(self.x_s, self.y_s, self.x_m_1, self.y_e)
        return s1 - s2

#==============================================================================
class HaarFeatureHorizontalThreeSegments(HaarFeature):
        
    def __init__(self, x, y, w, h):
        assert(w % 3 == 0)
        assert(x >= 0)
        assert(y >= 0)
        assert(h >= 2)
        assert(w >= 3)
        
        self.y_s  = y
        self.y_e  = y + h - 1
    
        self.x_s  = x
        self.x_m1 = x + w // 3
        self.x_m2 = x + 2 * w // 3 - 1
        self.x_e  = x + w - 1
        
    def compute_value(self, integral_image):
        s1 = integral_image.sum(self.x_s,  self.y_s,  self.x_e,  self.y_e)
        s2 = integral_image.sum(self.x_m1, self.y_s,  self.x_m2, self.y_e)
        return s1 - 2*s2

#==============================================================================
class HaarFeatureFourSegments(HaarFeature):
    def __init__(self, x, y, w, h):
        assert(h % 2 == 0)
        assert(w % 2 == 0)
        assert(x >= 0)
        assert(y >= 0)
        assert(w >= 2)
        assert(h >= 2)
        
        self.x_s   = x
        self.x_m   = x + w // 2
        self.x_m_1 = x + w // 2 - 1
        self.x_e   = x + w - 1
        
        self.y_s   = y
        self.y_m   = y + h // 2
        self.y_m_1 = y + h // 2 - 1
        self.y_e   = y + h - 1
        
    def compute_value(self, integral_image):
        
        s1 = integral_image.sum(self.x_s, self.y_s, self.x_e,   self.y_e  )
        s2 = integral_image.sum(self.x_s, self.y_m, self.x_m_1, self.y_e  )
        s3 = integral_image.sum(self.x_m, self.y_s, self.x_e,   self.y_m_1)
        
        return s1 - 2*s2 - 2*s3

#==============================================================================
# Сохраним все возможные признаки

features_to_use = [HaarFeatureVerticalTwoSegments, 
                   HaarFeatureVerticalThreeSegments, 
                   HaarFeatureHorizontalTwoSegments,
                   HaarFeatureHorizontalThreeSegments,
                   HaarFeatureFourSegments]
# шаги по x,y,w,h
x_stride = 2
y_stride = 2
w_stride = 2
h_stride = 2

all_features = []
for x in range(0, image_canonical_size, x_stride):
    for y in range(0, image_canonical_size, y_stride):
        for w in range(2, image_canonical_size - x + 1, w_stride):
            for h in range(2, image_canonical_size - y + 1, h_stride):
                for feature_type in features_to_use:
                    try:
                        feature = feature_type(x, y, w, h)
                        all_features.append(feature)
                    except:
                        continue
print("Всего признаков: {}".format(len(all_features)))         

#==============================================================================
# Вычислим все признаки на всех изображениях

def compute_features_for_image(integral_image, features):
    result = np.zeros(len(features))
    for ind, feature in enumerate(features):
        result[ind] = feature.compute_value(integral_image)
    return result

#==============================================================================
def _compute_features(integral_images, features):
    result = np.zeros((len(integral_images), len(features)))
    bar = progressbar.ProgressBar(maxval = len(integral_images))
    
    bar.start()
    for ind, integral_image in enumerate(bar(integral_images)):
        result[ind] = compute_features_for_image(integral_image, features)
        bar.update(ind+1)
    return result

#==============================================================================
def compute_features(integral_images, features, ftr_file):
    if os.path.isfile(ftr_file):    
        return np.load(ftr_file)
    else:
        ret = _compute_features(integral_images, features)
        np.save(ftr_file, ret)
        return ret

#==============================================================================
print('Will compute features...')
positive_features = compute_features(integral_positives, all_features, 'data/pos.npy')
negative_features = compute_features(integral_negatives, all_features, 'data/neg.npy')
print('Done!')

#==============================================================================
# Подготовим тренировочный набор

print('Will prepare train set...')
y_positive = np.ones(len(positive_features))
y_negative = np.zeros(len(negative_features))
    
X_train = np.concatenate((positive_features, negative_features))
y_train = np.concatenate((y_positive, y_negative))
print('Done!')

#==============================================================================
# Базовый классификатор

class DecisionStump:
    def __init__(self, threshold = 0, polarity = 1):
        self.threshold = threshold
        self.polarity = polarity
        
    def train(self, X, y, w, indices):
        '''
            Функция осуществляет обучение слабого классификатора
            
            На входе:
                X -- одномерный отсортированный numpy массив со значениями признака
                y -- одномерный numpy массив со значением класса для примера (0|1)
                Порядок y -- до сортировки X
                w -- одномерный numpy массив со значением весов признаков
                Порядок w -- до сортировки X
                indices -- одномерный numpy массив, перестановка [несортированный X] -> [сортированный X]
                Массив indices нужен для оптимизации,
                чтобы не сортировать X каждый раз, мы предсортируем значения признаков
                для всех примеров. При этом мы сохраняем отображение между сортированными
                и изначальными индексами, чтобы знать соответствие между x, y и w

                indices[i] == изначальный индекс элемента, i-го в порядке сортировки
            
            На выходе:
            
            численное значение ошибки обученного классификатора
        '''
        w = np.take(w, indices)
        y = np.take(y, indices)
            
        
        # Какой ужас!
        # Так и хочется переписать на Си!
        def _learn(X, y, w):
            
            s1 = y*w
            s1[1:] = s1[:-1]
            s1[0] = 0
            s1 = np.cumsum(s1)

            y = (y == 0).astype(y.dtype)
            s2 = y*w
            s2 = np.flipud(s2)
            s2 = np.cumsum(s2)
            s2 = np.flipud(s2)
            
            error = s1 + s2 
            
            n = np.argmin(error)
            
            return X[n], error[n]
        # Ужас!

        x_pos, e_pos = _learn(X, y, w)
        
        X = np.flipud(X)
        y = np.flipud(y)
        w = np.flipud(w)
        
        x_neg, e_neg = _learn(X, y, w)

        if e_pos <= e_neg:
            self.threshold = x_pos
            self.polarity  = 1
            error = e_pos
        else:
            self.threshold = x_neg
            self.polarity  = -1
            error = e_neg
            
        return error
                
    def classify(self, x):
        return np.array(self.polarity * x >= self.polarity * self.threshold).astype('int')
        #return 1 if self.polarity * x >= self.polarity * self.threshold else 0
    
    def __repr__(self):
        return "Threshold: {}, polarity: {}".format(self.threshold, self.polarity)

#==============================================================================
def train_classifier(classifier_type, X, y, w, indices):
    classifier = classifier_type()
    error = classifier.train(X, y, w, indices)
    return error, classifier

#==============================================================================
def learn_best_classifier(classifier_type, X, y, w, all_features, indices):
    '''
    Функция находит лучший слабый классификатор
    
    На входе:
        classifier_type -- класс классификатора (DecisionStump в нашем случае)
        X -- двумерный numpy массив, где X[i, j] -- значение признака i для примера j
        Каждый X[i] отсортирован по возрастанию
        y -- одномерный numpy массив с классом объекта (0|1). Порядок y соответствует порядку примеров в датасете
        w -- одномерный numpy массив весов для каждого примера. Порядок w соответствует порядку примеров в датасете
        all_features -- список описаний признаков
        indices -- список одномерных numpy массивов. 
        indices[i, j] == изначальный индекс элемента, j-го в порядке сортировки для i-го признака
        
    На выходе:
        best_classifier -- лучший слабый классификатор
        best_error -- его ошибка
        best_feature -- признак, на котором он был обучен (одна из HaarFeatures)
        predictions -- предсказания классификатора (в порядке до сортировки)
    '''    
    # натренируем каждый классификатор по каждому признаку
    errors  = []
    classes = []
    
    bar = progressbar.ProgressBar(maxval = len(all_features))
    
    for i in bar(range(0, len(all_features))):

        err, cls = train_classifier(classifier_type, X[i,:], y, w, indices[i,:])
        # Добавляем в списки
        errors.append(err)
        classes.append(cls)
    
    # выберем наилучший и сохраним лучший классификатор, ошибку, признак и индекс признака в 
    # best_classifier, best_error, best_feature, best_feature_ind
    # Как то так:
    # https://stackoverflow.com/questions/2474015/getting-the-index-of-the-returned-max-or-min-item-using-max-min-on-a-list
    i = np.array(errors).argmin()
    
    best_feature_ind = i
    best_feature     = all_features[i]
    best_error       = errors[i]
    best_classifier  = classes[i]
    
    # вернем также предсказания лучшего классификатора
    predictions = np.zeros(len(y))
    for j in range(0, len(y)):
        predictions[indices[best_feature_ind][j]] = best_classifier.classify(X[best_feature_ind][j])
    return best_classifier, best_error, best_feature, predictions

#==============================================================================
# Бустинговый классификатор

class BoostingClassifier:
    def __init__(self, classifiers, weights, features, threshold = None):
        self.classifiers = classifiers
        self.weights = weights
        self.features = features
        self.threshold = sum(weights) / 2 if threshold is None else threshold
    
    def classify(self, X, ret_qa = False):
        '''
        На входе:
        X -- одномерный numpy вектор признаков

        На выходе:
        1, если ансамбль выдает значение больше threshold и 0 если меньше
        '''
        res = 0.0
        for classifier, weight, feature in zip(self.classifiers, self.weights, self.features):
            res += weight * classifier.classify(feature.compute_value(X))
            
        ret_val = int(res > self.threshold)
            
        if ret_qa:
            return ret_val, res/self.threshold
        else:
            return ret_val

#==============================================================================
# Обучение методом бустинга

def learn_face_detector(X, y, rounds = 200, eps = 1e-15):
    '''
    На входе:
        X -- двумерный numpy массив, X[i,j] == значение признака j для примера i
        y -- одномерный numpy массив с классом объекта (0|1)
        rounds -- максимальное количество раундов обучения
        eps -- критерий останова (алгоритм останавливается, если новый классификатор имеет ошибку меньше eps)

    На выходе:
        классификатор типа BoostingClassifier
    '''
    # Транспонируем матрицу пример-признак к матрицу признак-примеры
    print('Transpose X...')
    X_t = X.copy().T
    indices = np.zeros(X_t.shape).astype(int)
    print('Done!\nSort X[i]...')
    # Предсортируем каждый признак, но сохраним соответствие между индексами
    # в массиве indices для каждого прзинака
    bar = progressbar.ProgressBar(maxval = len(X_t))
    for index in bar(range(0, len(X_t))):
        indices[index] = X_t[index].argsort()
        X_t[index].sort()
    print('Done!\nInitiate learning procedure...')
    
    # найдем количество положительных примеров в выборке
    n_positive = np.sum((y > 0).astype('int'))
    # найдем количество отрицательных примеров в выборке
    n_negative = len(y) - n_positive
    # инициализируем веса
    w = (1.0 / float(n_positive)) * (y == 1).astype('float') + (1.0 / float(n_negative)) * (y == 0).astype('float')
    print('Done!\nWill train the classifier...')
    classifiers = []
    features = []
    alpha = []
    for round in range(0, rounds):
        print("Раунд {}".format(round))
        # нормируем веса так, чтобы сумма была равна 1
        w /= np.sum(w)
        # найдём лучший слабый классификатор
        weak_classifier, error, feature, weak_classifier_predictions = learn_best_classifier(DecisionStump, X_t, y, w, all_features, indices)
        print("Взвешенная ошибка текущего слабого классификатора: {}".format(error))
        # если ошибка уже почти нулевая, остановимся
        if error < eps:
            break
        
        # найдем beta
        beta = error / (1.0 - error)
        # e[i] == 0 если классификация правильная и 1 наоборот
        e  = (y != weak_classifier_predictions).astype('float')
        ne = 1.0 - e
        # каждый правильно классифицированный вес нужно домножить на beta 
        w *= (e + beta*ne)#np.power(beta, 1.0 - e)
        # добавим к ансамблю новый классификатор с его весом и признаком
        classifiers.append(weak_classifier)
        features.append(feature)
        alpha.append(math.log(1 / beta))
        
        # посчитаем промежуточную точность
        strong_classifier = BoostingClassifier(classifiers, alpha, features)
        pos_predictions = [strong_classifier.classify(im) for im in integral_positives]
        neg_predictions = [strong_classifier.classify(im) for im in integral_negatives]
        correct_positives = float(sum(pos_predictions)) / float(len(pos_predictions))
        correct_negatives = 1.0 - float(sum(neg_predictions)) / float(len(neg_predictions))
        print("Корректно классифицированные лица {}".format(correct_positives))
        print("Корректно классифицированные не-лица {}".format(correct_negatives))
    print('Done!')
    return BoostingClassifier(classifiers, alpha, features)

#==============================================================================
strong_classifier = learn_face_detector(X_train, y_train, rounds = 100)

#==============================================================================
# Посчитаем точность
negatives_prepared_new = prepare_negatives(negatives, 10000, image_canonical_size)

pred_neg_new = [strong_classifier.classify(IntegralImage(im)) for im in negatives_prepared_new]

false_positive_rate = sum(pred_neg_new) / len(pred_neg_new)
print("Процент ложных обнаружений: {}".format(false_positive_rate * 100))

#==============================================================================
test = get_all_images('data/test', 'test_img.npy')

test_prepared = prepare_positives(test, image_canonical_size)

test_positives_result = [strong_classifier.classify(IntegralImage(im)) for im in test_prepared]
detection_rate = sum(test_positives_result) / len(test_positives_result)
print("Процент корректных обнаружений: {}".format(detection_rate * 100))

#==============================================================================
# Калибрация классификатора
pivot_thr = 0.5*sum(strong_classifier.weights)

thr     = []
fls_pos = []
rate    = 0.125
N       = 10

bar = progressbar.ProgressBar(maxval =  N)
for i in bar(range(0, N + 1)):
    
    # Не хочется делать полный брутфорс
    cur_thr = pivot_thr * (1 + rate * (i / N - 0.5))
    
    strong_classifier.threshold = cur_thr
    
    test_positives_result = [strong_classifier.classify(IntegralImage(im)) for im in test_prepared]
    detection_rate = sum(test_positives_result) / len(test_positives_result)
      
    if detection_rate > 0.9:
        pred_neg_new = [strong_classifier.classify(IntegralImage(im)) for im in negatives_prepared_new]
        false_positive_rate = sum(pred_neg_new) / len(pred_neg_new)
        fls_pos.append(false_positive_rate)
        thr.append(cur_thr)
        
i = np.array(fls_pos).argmin()

print("Процент ложных обнаружений: {}".format(fls_pos[i] * 100))

# В конце установить подходящее значение порога
strong_classifier.threshold = thr[i]

#==============================================================================
# Воспользуемся полученным классификатором, чтобы найти лица на изображении

images_to_scan = get_all_images('data/for_scanning', 'data/for_scan_img.npy')

#==============================================================================
# примерный скелет программы (наивная реализация)

def detect_faces(image, classifier):
    norm_image = normalize_image(image)
    w, h = norm_image.shape
    # лучше задавать не абсолютные размеры окна, а относительные (в процентах)
    window_sizes = [0.15, 0.2, 0.25]
    results = []
    for w_size in window_sizes:
        bar = progressbar.ProgressBar()
        for x in bar(range(0, w, 5)):
            for y in range(0, h, 5):
                xc = x + int(h * w_size)
                yc = y + int(w * (2/3) * w_size) #2/3 - пропорции лица по ширине/высоте
                if xc < w and yc < h:
                    crop = norm_image[x:xc,y:yc]
                    # здесь необходимо нормализовать изображение и применить классификатор
                    # если классификатор детектирует лицо, нужно добавить (x, y, xc, yc) к списку result
                    crop_resized = resize(crop, (image_canonical_size, image_canonical_size), mode='constant').astype(np.float32)
                    is_face, face_qa = classifier.classify(IntegralImage(crop_resized), ret_qa = True)
                    
                    if is_face:
                        results.append((x, y, xc, yc, face_qa))
    
    return results

result = detect_faces(images_to_scan[0], strong_classifier)



print(thr[i])

np.save('detected_quarter.npy', np.array(result))
print(np.load('detected_quarter.npy'))

im = images_to_scan[0]

fig,ax = plt.subplots(1)
fig.set_size_inches(20,20)
ax.imshow(im, cmap='gray')



for x, y, xc, yc, qa in result:
    ecl = cl.hsv_to_rgb(np.array([(qa-1)*2, 1.0, 1.0]))
    rect = patches.Rectangle((y,x),yc - y,xc - x,linewidth=1,edgecolor=ecl,facecolor='none')
    ax.add_patch(rect)

plt.show()
